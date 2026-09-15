import json
import hashlib
import time
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
from core.utils import MAX_AI_AUDIO_BYTES, valid_uploaded_file
from core.analytics import track
from .services.response_contract import AIResponse, public_metadata, request_id_from
from .tools import run_tool
from .tools.router import route as route_intent
from .tools.present import present

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
        claim_token = data.get('claim_token', '')

        if not user_message:
            return JsonResponse({'error': 'Message is required'}, status=400)
        if len(user_message) > 1000:
            return JsonResponse({'error': 'Message too long (max 1000 chars)'}, status=400)

        # Tool dispatch — deterministic routing into a least-privilege tool.
        # Placed before the response cache on purpose: tool results are
        # per-citizen, and the ai_resp_ cache below is keyed on message text
        # alone, so a routed reply must return before it can be stored (I-1).
        _routed = route_intent(user_message, claim_token=claim_token)
        if _routed:
            _tool_name, _tool_kwargs = _routed
            _tool_result = run_tool(_tool_name, request, **_tool_kwargs)
            _reply, _followups = present(_tool_name, _tool_result)
            if _reply is not None:
                return JsonResponse({
                    'response': _reply,
                    'conversation_id': None,
                    'message_id': None,
                    'sources': [],
                    'intent': _tool_name,
                    'followups': _followups,
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
                    **public_metadata(
                        sources=_cached.get('sources', []),
                        source=_cached.get('source', 'primary'),
                        source_note=_cached.get('source_note'),
                        fallback=_cached.get('fallback', False),
                        degraded=_cached.get('degraded', False),
                        citations=_cached.get('citations', []),
                    ),
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
                    fallback_meta = fallback_result.get('metadata', {})
                    result = {
                        'response':   fallback_result['answer'],
                        'sources':    fallback_meta.get('sources', ['knowledge_base']),
                        'intent':     engine._detect_intent(user_message),
                        'followups':  [],
                        'source_note': fallback_meta.get('source_note') or 'Answered from local records',
                        'source': fallback_result.get('source', 'local_db'),
                        'fallback': True,
                        'degraded': True,
                        'citations': fallback_meta.get('citations', []),
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
                        **public_metadata(
                            sources=result['sources'],
                            source='fallback',
                            source_note=result.get('source_note'),
                            fallback=True,
                            degraded=True,
                            citations=result.get('citations', []),
                            request_id=request_id_from(request),
                        ),
                    })

        started = time.perf_counter()
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
                fallback_meta = fallback_result.get('metadata', {})
                result['response'] = fallback_result['answer']
                result['sources'] = fallback_meta.get('sources', result.get('sources', []))
                result['source'] = fallback_result.get('source', 'local_db')
                result['source_note'] = fallback_meta.get('source_note') or 'Answered from local records'
                result['fallback'] = True
                result['degraded'] = True
                result['citations'] = fallback_meta.get('citations', [])
                source_note = result['source_note']

        # Keep operational metadata in one internal contract without adding
        # fields to the established JSON response.
        response_contract = AIResponse(
            answer=result['response'],
            sources=result.get('sources', []),
            source_note=source_note,
            degraded=bool(source_note),
            fallback=bool(source_note),
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
            request_id=request_id_from(request),
            metadata={'intent': result.get('intent', 'general')},
        )
        source_note = response_contract.source_note

        ai_msg = None
        if result.get('response', '').strip():
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
                'source': result.get('source') or ('fallback' if source_note else 'primary'),
                'source_note': source_note or result.get('source_note'),
                'fallback': bool(source_note) or result.get('fallback', False),
                'degraded': bool(source_note) or result.get('degraded', False),
                'citations': result.get('citations', []),
            }, 3600)

        return JsonResponse({
            'response':        result['response'],
            'conversation_id': conversation.id,
            'message_id':      ai_msg.id if ai_msg else None,
            'sources':         result['sources'],
            'intent':          result['intent'],
            'followups':       result.get('followups', []),
            'source_note':     source_note,
            **public_metadata(
                sources=result.get('sources', []),
                source=result.get('source') or ('fallback' if source_note else 'primary'),
                source_note=source_note or result.get('source_note'),
                fallback=bool(source_note) or result.get('fallback', False),
                degraded=bool(source_note) or result.get('degraded', False),
                citations=result.get('citations', []),
                latency_ms=response_contract.latency_ms,
                request_id=response_contract.request_id,
            ),
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
        started    = time.perf_counter()
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
        final_meta = {
            **public_metadata(
                sources=final_meta.get('sources', []),
                source=final_meta.get('source'),
                source_note=final_meta.get('source_note'),
                fallback=final_meta.get('fallback', False),
                degraded=final_meta.get('degraded', False),
                citations=final_meta.get('citations', []),
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                request_id=request_id_from(request),
            ),
            'intent': final_meta.get('intent', 'general'),
            'followups': final_meta.get('followups', []),
        }
        ai_msg = None
        if full_text.strip():
            ai_msg = Message.objects.create(
                conversation=conversation,
                role=Message.ROLE_ASSISTANT,
                content=full_text,
                sources=final_meta['sources'],
                intent=final_meta['intent'],
            )
        conversation.save()

        yield f"data: {json.dumps({'done': True, 'conversation_id': conversation.id, 'message_id': ai_msg.id if ai_msg else None, 'response': full_text, **final_meta})}\n\n"

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
    if not valid_uploaded_file(audio_file, MAX_AI_AUDIO_BYTES, 'audio/'):
        return JsonResponse({'error': 'Audio file is too large or invalid.'}, status=400)

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
        claim_token = data.get('claim_token', '')
        if not user_message:
            return JsonResponse({'error': 'Message is required'}, status=400)
        if len(user_message) > 1000:
            return JsonResponse({'error': 'Message too long (max 1000 chars)'}, status=400)

        # Routed tool answers are synchronous database reads — no Groq call,
        # so there is nothing to poll for. Returning here also keeps per-citizen
        # results out of the message-keyed ai_resp_ cache below (I-1).
        _routed = route_intent(user_message, claim_token=claim_token)
        if _routed:
            _tool_name, _tool_kwargs = _routed
            _tool_result = run_tool(_tool_name, request, **_tool_kwargs)
            _reply, _followups = present(_tool_name, _tool_result)
            if _reply is not None:
                return JsonResponse({
                    'response': _reply,
                    'job_id': None,
                    'cached': False,
                    'status': 'done',
                    'sources': [],
                    'intent': _tool_name,
                    'followups': _followups,
                })

        _msg_norm = user_message.lower().strip()[:200].rstrip('?.! ')
        _hash = hashlib.sha256(_msg_norm.encode()).hexdigest()[:24]
        _cached = _cache.get(f'ai_resp_{_hash}')
        if _cached:
            return JsonResponse({
                **_cached,
                'job_id': None,
                'cached': True,
                'source': _cached.get('source', 'primary'),
                'source_note': _cached.get('source_note'),
                'fallback': _cached.get('fallback', False),
                'degraded': _cached.get('degraded', False),
                'citations': _cached.get('citations', []),
            })

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
            except (Conversation.DoesNotExist, ValueError, TypeError):
                return JsonResponse({'error': 'Conversation not found'}, status=404)

        from .tasks import process_chat_async
        try:
            process_chat_async.delay(
                job_id=job_id,
                user_message=user_message,
                history=history,
                user_id=request.user.pk if request.user.is_authenticated else None,
                conversation_id=conversation_id,
                session_key=request.session.session_key,
                is_staff=request.user.is_staff,
                claim_token=claim_token,
            )
            return JsonResponse({'job_id': job_id, 'status': 'queued'})
        except Exception:
            # Redis/Celery unavailable — fall back to synchronous path, but still
            # persist the conversation so history and feedback are not lost.
            import logging as _log
            _log.getLogger(__name__).warning('Celery unavailable — chat_async running synchronously')

            user_obj = request.user if request.user.is_authenticated else None

            # Get or create the conversation so messages are persisted.
            if not request.session.session_key:
                request.session.create()
            if conversation_id:
                try:
                    if user_obj:
                        conv = Conversation.objects.get(id=conversation_id, user=user_obj)
                    else:
                        conv = Conversation.objects.get(
                            id=conversation_id,
                            session_key=request.session.session_key,
                        )
                except Conversation.DoesNotExist:
                    conv = None
            else:
                conv = None

            if conv is None:
                conv = Conversation.objects.create(
                    user=user_obj,
                    session_key=request.session.session_key,
                    title=user_message[:50],
                )

            Message.objects.create(
                conversation=conv,
                role=Message.ROLE_USER,
                content=user_message,
            )

            engine = MunicipalAIEngine()
            result = engine.chat(user_message, history, user=user_obj)

            ai_msg = None
            if result.get('response', '').strip():
                ai_msg = Message.objects.create(
                    conversation=conv,
                    role=Message.ROLE_ASSISTANT,
                    content=result['response'],
                    sources=result.get('sources', []),
                    intent=result.get('intent', ''),
                )
            conv.save()

            return JsonResponse({
                'job_id': None,
                'status': 'done',
                'response': result['response'],
                'sources': result.get('sources', []),
                'intent': result.get('intent', ''),
                'followups': result.get('followups', []),
                'conversation_id': conv.id,
                'message_id': ai_msg.id if ai_msg else None,
                **public_metadata(
                    sources=result.get('sources', []),
                    source=result.get('source'),
                    source_note=result.get('source_note'),
                    fallback=result.get('fallback', False),
                    degraded=result.get('degraded', False),
                    citations=result.get('citations', []),
                    request_id=request_id_from(request),
                ),
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
