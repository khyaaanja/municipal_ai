import json
import hashlib
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import ensure_csrf_cookie
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.core.cache import cache
from .models import Conversation, Message
from .ai_engine import MunicipalAIEngine
from core.utils import get_client_ip
from core.analytics import track

try:
    from .services.answer_engine import AnswerEngine, get_answer_engine, is_degraded_response
    _answer_engine_available = True
except Exception:  # pragma: no cover — keeps view importable if service fails to import
    _answer_engine_available = False


def _answer_with_fallback(request, user_message, history, user=None):
    """
    Re-answer a query using the AnswerEngine's local-DB fallback path.

    Called only after the primary engine produced a degraded/error response —
    so Groq is already known to be failing. We open the circuit breaker first
    so `engine.answer()` skips the dead API and goes straight to the local
    database fallback (no retry storm).

    Returns the engine result dict {answer, source, degraded} or None if the
    fallback itself can't produce a usable answer.
    """
    try:
        from .services.answer_engine import LocalRetrieverAdapter, open_circuit

        # Groq already failed in the primary path → open breaker so the
        # fallback engine skips straight to local records for this and the
        # next CIRCUIT_TIMEOUT seconds.
        open_circuit()

        retriever = LocalRetrieverAdapter()
        engine = get_answer_engine(retriever=retriever)
        return engine.answer(user_message)
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Fallback answer failed')
        return None


@ensure_csrf_cookie
def chat_page(request):
    context = {
        'page_title': 'AI City Assistant',
        'initial_query': request.GET.get('q', ''),
    }
    if request.user.is_authenticated:
        conversations = Conversation.objects.filter(
            user=request.user, is_active=True
        ).order_by('-updated_at')[:10]
        context['conversations'] = conversations
    return render(request, 'chatbot/chat.html', context)


# ---------------------------------------------------------------------------
# Rate-limit helper
# ---------------------------------------------------------------------------

def _check_rate_limit(ip: str, key_prefix: str, limit: int, window: int = 3600) -> bool:
    """Return True if rate limit exceeded."""
    key = f'{key_prefix}_{ip}'
    try:
        count = cache.incr(key)
    except ValueError:
        cache.set(key, 1, window)
        count = 1
    return count > limit


# ---------------------------------------------------------------------------
# Chat API (non-streaming, backward compatible)
# ---------------------------------------------------------------------------

@require_http_methods(["POST"])
def chat_api(request):
    ip = get_client_ip(request)
    if _check_rate_limit(ip, 'chat_api', 120):
        return JsonResponse({'error': 'Rate limit exceeded. Try again later.'}, status=429)

    try:
        data         = json.loads(request.body)
        user_message = data.get('message', '').strip()
        conversation_id = data.get('conversation_id')

        if not user_message:
            return JsonResponse({'error': 'Message is required'}, status=400)
        if len(user_message) > 1000:
            return JsonResponse({'error': 'Message too long (max 1000 chars)'}, status=400)

        # Fast-path: complaint status lookup
        import re as _re
        _cid_match = _re.search(r'\b(BK-[A-Z0-9]{6,10})\b', user_message.upper())
        if _cid_match or 'check status of my complaint' in user_message.lower():
            if _cid_match:
                try:
                    from complaints.models import Complaint as _Complaint
                    c = _Complaint.objects.get(complaint_id=_cid_match.group(1))
                    status_text = dict(_Complaint.STATUS_CHOICES).get(c.status, c.status)
                    reply = (
                        f"**Complaint {c.complaint_id}** found!\n\n"
                        f"**Status:** {status_text}\n"
                        f"**Category:** {c.get_category_display()}\n"
                        f"**Title:** {c.title}\n"
                        f"**Filed:** {c.created_at.strftime('%b %d, %Y')}\n\n"
                        f"Track full details: [{c.complaint_id}](/complaint/status/{c.complaint_id}/)"
                    )
                except Exception:
                    reply = (
                        f"I couldn't find a complaint with ID **{_cid_match.group(1)}**. "
                        f"Please double-check the ID (format: BK-XXXXXX) and try again. "
                        f"You can also [track your complaint here](/complaint/status/)."
                    )
            else:
                reply = (
                    "To check your complaint status, please enter your complaint ID. "
                    "It looks like **BK-XXXXXX** (shown after you submitted). "
                    "For example: `check BK-ABC123`\n\n"
                    "Or [visit the status page](/complaint/status/) and enter your ID there."
                )
            return JsonResponse({
                'response': reply, 'conversation_id': None,
                'message_id': None, 'sources': [], 'intent': 'complaint_status',
                'followups': ['How do I submit a new complaint?', 'What happens after I file a complaint?'],
            })

        # Fast-path: civic issue keyword detection
        _msg_lower = user_message.lower()
        _civic_map = {
            'ROAD':           ['pothole', 'broken road', 'road damage', 'road crack', 'bad road', 'road repair', 'road issue', 'road problem'],
            'SANITATION':     ['garbage', 'trash', 'waste', 'litter', 'dirty street', 'garbage collection', 'bin overflow', 'dump site', 'rubbish'],
            'WATER':          ['water leak', 'no water', 'water cut', 'dirty water', 'water pipe', 'water supply', 'flooding', 'water problem'],
            'ELECTRICITY':    ['power cut', 'no electricity', 'blackout', 'electricity outage', 'power failure', 'power problem', 'no light', 'streetlight broken'],
            'NOISE':          ['loud noise', 'noise pollution', 'noise complaint', 'noise problem', 'noisy neighbor'],
            'INFRASTRUCTURE': ['broken bridge', 'drainage blocked', 'sewer', 'blocked drain', 'footpath broken', 'pavement damaged'],
        }
        _detected_category = None
        for _cat, _keywords in _civic_map.items():
            for _kw in _keywords:
                if _kw in _msg_lower:
                    _detected_category = _cat
                    break
            if _detected_category:
                break
        if _detected_category:
            _cat_label = {
                'ROAD': 'Road / Pavement', 'SANITATION': 'Sanitation / Waste',
                'WATER': 'Water Supply', 'ELECTRICITY': 'Electricity',
                'NOISE': 'Noise Pollution', 'INFRASTRUCTURE': 'Infrastructure',
            }.get(_detected_category, _detected_category.capitalize())
            reply = (
                f"It sounds like you're reporting a **{_cat_label}** issue. "
                f"You can file an official complaint with Bhaktapur Municipality — "
                f"it will be tracked and forwarded to the responsible ward chairperson.\n\n"
                f"[📝 Report this issue now](/complaint/?category={_detected_category})\n\n"
                f"Once submitted you'll receive a reference number (BK-XXXXXX) to track progress. "
                f"Is there anything else I can help you with?"
            )
            return JsonResponse({
                'response': reply, 'conversation_id': None,
                'message_id': None, 'sources': [], 'intent': 'civic_issue',
                'followups': ['How do I track my complaint?', 'What happens after I submit?'],
            })

        # Response cache for anonymous informational queries
        _cache_key = None
        if not conversation_id:
            _msg_norm = user_message.lower().strip()[:200].rstrip('?.! ')
            _cache_key = 'ai_resp_' + hashlib.sha256(_msg_norm.encode()).hexdigest()[:24]
            _cached = cache.get(_cache_key)
            if _cached:
                return JsonResponse({
                    'response':  _cached['response'],
                    'conversation_id': None,
                    'message_id': None,
                    'sources':   _cached.get('sources', []),
                    'intent':    _cached.get('intent', 'cached'),
                    'followups': _cached.get('followups', []),
                })

        # Get or create conversation
        conversation = None
        if conversation_id:
            try:
                if request.user.is_authenticated:
                    conversation = Conversation.objects.get(id=conversation_id, user=request.user)
                else:
                    if not request.session.session_key:
                        request.session.create()
                    conversation = Conversation.objects.get(id=conversation_id, session_key=request.session.session_key)
            except Conversation.DoesNotExist:
                pass

        if not conversation:
            if not request.session.session_key:
                request.session.create()
            conversation = Conversation.objects.create(
                user=request.user if request.user.is_authenticated else None,
                session_key=request.session.session_key,
                title=user_message[:50]
            )

        history = list(
            conversation.messages
            .filter(role__in=['user', 'assistant'])
            .order_by('created_at')
            .values('role', 'content')
        )

        Message.objects.create(
            conversation=conversation,
            role=Message.ROLE_USER,
            content=user_message
        )

        engine = MunicipalAIEngine()

        # ── Circuit breaker: skip Groq call if it's been failing recently ──
        if _answer_engine_available:
            from .services.answer_engine import is_circuit_open
            if is_circuit_open():
                fallback_result = _answer_with_fallback(
                    request, user_message, history, user=request.user
                )
                if fallback_result and fallback_result.get('answer'):
                    result = {
                        'response':   fallback_result['answer'],
                        'sources':    ['knowledge_base'],
                        'intent':     'general',
                        'followups':  [],
                        'source_note': 'Answered from local records',
                    }
                    ai_msg = Message.objects.create(
                        conversation=conversation,
                        role=Message.ROLE_ASSISTANT,
                        content=result['response'],
                        sources=result['sources'],
                        intent=result['intent'],
                    )
                    conversation.save()
                    track(request, 'chat', object_type='conversation', object_id=conversation.id)
                    return JsonResponse({
                        'response':        result['response'],
                        'conversation_id': conversation.id,
                        'message_id':      ai_msg.id,
                        'sources':         result['sources'],
                        'intent':          result['intent'],
                        'followups':       result.get('followups', []),
                        'source_note':     result.get('source_note'),
                    })

        result = engine.chat(user_message, history, user=request.user)

        # ── Fallback layer ──────────────────────────────────────────────────
        # If the primary engine already produced a degraded/error response
        # (Groq down, rate-limited, timeout), re-answer from local records so
        # the user still gets a real answer instead of a generic failure.
        source_note = None
        if _answer_engine_available and is_degraded_response(result.get('response', '')):
            fallback_result = _answer_with_fallback(
                request, user_message, history, user=request.user
            )
            if fallback_result and fallback_result.get('answer'):
                result['response'] = fallback_result['answer']
                source_note = 'Answered from local records'

        ai_msg = Message.objects.create(
            conversation=conversation,
            role=Message.ROLE_ASSISTANT,
            content=result['response'],
            sources=result['sources'],
            intent=result['intent']
        )

        conversation.save()
        track(request, 'chat', object_type='conversation', object_id=conversation.id)

        if _cache_key and not data.get('conversation_id'):
            cache.set(_cache_key, {
                'response':  result['response'],
                'sources':   result['sources'],
                'intent':    result['intent'],
                'followups': result.get('followups', []),
            }, 3600)

        return JsonResponse({
            'response':        result['response'],
            'conversation_id': conversation.id,
            'message_id':      ai_msg.id,
            'sources':         result['sources'],
            'intent':          result['intent'],
            'followups':       result.get('followups', []),
            'source_note':     source_note,
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        if getattr(settings, 'DEBUG', False):
            return JsonResponse({'error': 'Internal server error', 'exception': str(e)}, status=500)
        return JsonResponse({'error': "I'm having trouble responding right now. Please try again in a moment."}, status=500)


# ---------------------------------------------------------------------------
# Streaming chat API (SSE)
# ---------------------------------------------------------------------------

@require_http_methods(["POST"])
def chat_stream(request):
    """Server-Sent Events streaming endpoint — delivers tokens as they arrive."""
    ip = get_client_ip(request)
    if _check_rate_limit(ip, 'chat_stream', 120):
        def _limit():
            yield f"data: {json.dumps({'error': 'Rate limit exceeded'})}\n\n"
        return StreamingHttpResponse(_limit(), content_type='text/event-stream')

    try:
        data         = json.loads(request.body)
        user_message = data.get('message', '').strip()
        conversation_id = data.get('conversation_id')
    except (json.JSONDecodeError, Exception):
        def _err():
            yield f"data: {json.dumps({'error': 'Invalid request'})}\n\n"
        return StreamingHttpResponse(_err(), content_type='text/event-stream')

    if not user_message or len(user_message) > 1000:
        def _err():
            yield f"data: {json.dumps({'error': 'Invalid message'})}\n\n"
        return StreamingHttpResponse(_err(), content_type='text/event-stream')

    # Get conversation history
    history = []
    conversation = None
    if conversation_id:
        try:
            if request.user.is_authenticated:
                conversation = Conversation.objects.get(id=conversation_id, user=request.user)
            else:
                if not request.session.session_key:
                    request.session.create()
                conversation = Conversation.objects.get(id=conversation_id, session_key=request.session.session_key)
            history = list(
                conversation.messages
                .filter(role__in=['user', 'assistant'])
                .order_by('created_at')
                .values('role', 'content')
            )
        except Conversation.DoesNotExist:
            pass

    if not conversation:
        if not request.session.session_key:
            request.session.create()
        conversation = Conversation.objects.create(
            user=request.user if request.user.is_authenticated else None,
            session_key=request.session.session_key,
            title=user_message[:50]
        )

    # Save user message upfront
    Message.objects.create(conversation=conversation, role=Message.ROLE_USER, content=user_message)

    user = request.user

    def event_stream():
        engine     = MunicipalAIEngine()
        full_text  = ''
        final_meta = {}

        # Head-start: send a brief typing indicator immediately so the frontend
        # renders the loading state before the engine even starts building context.
        yield f"data: {json.dumps({'token': ''})}\n\n"

        for kind, payload in engine.build_stream(user_message, history, user=user):
            if kind == 'token':
                full_text += payload
                yield f"data: {json.dumps({'token': payload})}\n\n"
            elif kind == 'meta':
                final_meta = payload

        # Save assistant response to DB
        ai_msg = Message.objects.create(
            conversation=conversation,
            role=Message.ROLE_ASSISTANT,
            content=full_text,
            sources=final_meta.get('sources', []),
            intent=final_meta.get('intent', 'general'),
        )
        conversation.save()

        yield f"data: {json.dumps({'done': True, 'conversation_id': conversation.id, 'message_id': ai_msg.id, **final_meta})}\n\n"

    response = StreamingHttpResponse(event_stream(), content_type='text/event-stream')
    response['Cache-Control']     = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response


# ---------------------------------------------------------------------------
# Voice transcription (Whisper)
# ---------------------------------------------------------------------------

@require_http_methods(["POST"])
def voice_transcribe(request):
    """Receive audio blob, transcribe with Whisper, return text."""
    ip = get_client_ip(request)
    if _check_rate_limit(ip, 'voice', 60):
        return JsonResponse({'error': 'Rate limit exceeded.'}, status=429)

    audio_file = request.FILES.get('audio')
    if not audio_file:
        return JsonResponse({'error': 'No audio file provided.'}, status=400)

    api_key = getattr(settings, 'GROQ_API_KEY', '')
    if not api_key:
        return JsonResponse({'error': 'AI service not configured.'}, status=503)

    try:
        from chatbot.ai_engine import _get_groq_client
        client      = _get_groq_client(api_key)
        model       = getattr(settings, 'GROQ_WHISPER_MODEL', 'whisper-large-v3')
        audio_bytes = audio_file.read()
        filename    = audio_file.name or 'voice.webm'

        transcription = client.audio.transcriptions.create(
            file=(filename, audio_bytes, audio_file.content_type or 'audio/webm'),
            model=model,
            response_format='text',
        )

        text = transcription.strip() if isinstance(transcription, str) else getattr(transcription, 'text', '').strip()
        if not text:
            return JsonResponse({'error': 'Could not transcribe audio. Please speak clearly and try again.'}, status=400)

        return JsonResponse({'text': text})

    except Exception as e:
        if getattr(settings, 'DEBUG', False):
            return JsonResponse({'error': str(e)}, status=500)
        return JsonResponse({'error': 'Transcription failed. Please try again.'}, status=500)


# ---------------------------------------------------------------------------
# Chat history & conversation management
# ---------------------------------------------------------------------------

@login_required
def chat_history(request):
    from django.core.paginator import Paginator
    from django.db.models import Prefetch
    convs = Conversation.objects.filter(
        user=request.user, is_active=True
    ).prefetch_related(
        Prefetch('messages', queryset=Message.objects.order_by('created_at'), to_attr='ordered_messages')
    ).order_by('-updated_at')
    total_messages = Message.objects.filter(conversation__user=request.user).count()
    paginator = Paginator(convs, 15)
    page = request.GET.get('page', 1)
    conversations = paginator.get_page(page)
    for conv in conversations:
        msgs = conv.ordered_messages
        user_msgs = [m for m in msgs if m.role == 'user']
        conv.first_message = user_msgs[0].content[:80] if user_msgs else ''
        conv.last_message  = msgs[-1].content[:90] if msgs else ''
        conv.message_count = len(msgs)
    return render(request, 'chatbot/history.html', {
        'conversations':      conversations,
        'total_conversations': paginator.count,
        'total_messages':     total_messages,
    })


@login_required
def conversation_detail(request, pk):
    try:
        conversation = Conversation.objects.get(id=pk, user=request.user)
        messages     = conversation.messages.all().order_by('created_at')
        return render(request, 'chatbot/conversation.html', {
            'conversation': conversation,
            'messages':     messages,
        })
    except Conversation.DoesNotExist:
        from django.http import Http404
        raise Http404


@login_required
def delete_conversation(request, pk):
    conv = get_object_or_404(Conversation, pk=pk, user=request.user)
    if request.method == 'POST':
        conv.delete()
        return JsonResponse({'success': True})
    return JsonResponse({'success': False}, status=405)


# ---------------------------------------------------------------------------
# Feedback loop
# ---------------------------------------------------------------------------

@require_http_methods(["POST"])
def message_feedback(request):
    try:
        data       = json.loads(request.body)
        message_id = data.get('message_id')
        rating     = data.get('rating')

        if not message_id or rating not in (1, -1):
            return JsonResponse({'error': 'message_id and rating (1 or -1) required'}, status=400)

        msg  = get_object_or_404(Message, pk=message_id, role=Message.ROLE_ASSISTANT)
        conv = msg.conversation

        if request.user.is_authenticated:
            if conv.user != request.user:
                return JsonResponse({'error': 'Not found'}, status=404)
        else:
            session_key = request.session.session_key or ''
            if conv.session_key != session_key:
                return JsonResponse({'error': 'Not found'}, status=404)

        from .models import ResponseFeedback
        if not request.session.session_key:
            request.session.create()
        session_key = request.session.session_key
        user = request.user if request.user.is_authenticated else None

        fb, created = ResponseFeedback.objects.get_or_create(
            message=msg,
            user=user,
            session_key='' if user else session_key,
            defaults={'rating': rating},
        )
        if not created:
            fb.rating = rating
            fb.save(update_fields=['rating'])

        if rating == -1:
            prev = msg.conversation.messages.filter(
                role=Message.ROLE_USER,
                created_at__lt=msg.created_at
            ).order_by('-created_at').first()
            if prev:
                from chatbot.models import UnansweredQuery
                normalized = ' '.join(prev.content.lower().split())[:300]
                obj, created = UnansweredQuery.objects.get_or_create(
                    normalized=normalized,
                    defaults={'query': prev.content},
                )
                if not created:
                    from django.db.models import F
                    UnansweredQuery.objects.filter(pk=obj.pk).update(
                        ask_count=F('ask_count') + 1,
                        query=prev.content,
                    )

        return JsonResponse({'success': True, 'created': created})

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception:
        return JsonResponse({'error': 'Server error'}, status=500)


# ---------------------------------------------------------------------------
# Language preference
# ---------------------------------------------------------------------------

@require_http_methods(["POST"])
@login_required
def set_language(request):
    try:
        data = json.loads(request.body)
        lang = data.get('language', 'en')
        valid_langs = ('en', 'ne', 'hi', 'zh-cn', 'bn')
        if lang not in valid_langs:
            return JsonResponse({'error': f'Invalid language. Supported: {", ".join(valid_langs)}'}, status=400)
        from .models import UserAIProfile
        UserAIProfile.objects.update_or_create(
            user=request.user,
            defaults={'preferred_language': lang},
        )
        return JsonResponse({'success': True, 'language': lang})
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)


# ---------------------------------------------------------------------------
# Async chat — queue Groq call via Celery, free up gunicorn threads
# ---------------------------------------------------------------------------

@require_http_methods(["POST"])
def chat_async(request):
    """
    Non-blocking chat.  Returns job_id instantly (< 50ms).
    Frontend polls /api/chat/poll/<job_id>/ every 1s until status == 'done'.
    """
    import uuid
    from django.core.cache import cache as _cache

    ip = get_client_ip(request)
    if _check_rate_limit(ip, 'chat_async', 120):
        return JsonResponse({'error': 'Rate limit exceeded. Try again later.'}, status=429)

    try:
        data         = json.loads(request.body)
        user_message = data.get('message', '').strip()
        if not user_message:
            return JsonResponse({'error': 'Message is required'}, status=400)
        if len(user_message) > 1000:
            return JsonResponse({'error': 'Message too long (max 1000 chars)'}, status=400)

        _hash = hashlib.md5(user_message.lower().encode()).hexdigest()
        _cached = _cache.get(f'chat_cache:{_hash}')
        if _cached:
            return JsonResponse({**_cached, 'job_id': None, 'cached': True})

        if not request.session.session_key:
            request.session.create()

        job_id = str(uuid.uuid4())
        conversation_id = data.get('conversation_id')
        history = []
        if conversation_id:
            try:
                from .models import Conversation
                if request.user.is_authenticated:
                    conv = Conversation.objects.get(id=conversation_id, user=request.user)
                else:
                    conv = Conversation.objects.get(id=conversation_id,
                                                     session_key=request.session.session_key)
                history = list(
                    conv.messages.filter(role__in=['user', 'assistant'])
                    .order_by('created_at').values('role', 'content')
                )
            except Exception:
                pass

        from .tasks import process_chat_async
        try:
            process_chat_async.delay(
                job_id=job_id,
                user_message=user_message,
                history=history,
                user_id=request.user.pk if request.user.is_authenticated else None,
                conversation_id=conversation_id,
                session_key=request.session.session_key,
            )
            return JsonResponse({'job_id': job_id, 'status': 'queued'})
        except Exception:
            # Redis/Celery unavailable — fall back to synchronous path
            engine = MunicipalAIEngine()
            result = engine.chat(user_message, history, user=request.user if request.user.is_authenticated else None)
            return JsonResponse({
                'job_id': None,
                'status': 'done',
                'response': result['response'],
                'sources': result.get('sources', []),
                'intent': result.get('intent', ''),
                'followups': result.get('followups', []),
                'conversation_id': None,
                'message_id': None,
            })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception:
        return JsonResponse({'error': 'Server error'}, status=500)


@require_http_methods(["GET"])
def chat_poll(request, job_id):
    """Poll for async chat result.  Call every ~1s until status != 'processing'."""
    import json as _json
    from django.core.cache import cache as _cache
    raw = _cache.get(f'chat_job:{job_id}')
    if raw is None:
        return JsonResponse({'status': 'pending'})
    try:
        return JsonResponse(_json.loads(raw))
    except Exception:
        return JsonResponse({'status': 'error', 'error': 'Corrupted job result'})
