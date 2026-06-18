import json
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.utils.decorators import method_decorator
from django.conf import settings
from django.core.cache import cache
from .models import Conversation, Message
from .ai_engine import MunicipalAIEngine
from core.utils import get_client_ip
from core.analytics import track



def chat_page(request):
    """Main chat interface."""
    context = {
        'page_title': 'AI City Assistant',
    }
    if request.user.is_authenticated:
        conversations = Conversation.objects.filter(
            user=request.user, is_active=True
        ).order_by('-updated_at')[:10]
        context['conversations'] = conversations
    return render(request, 'chatbot/chat.html', context)


@require_http_methods(["POST"])
def chat_api(request):
    """API endpoint for AI chat messages."""
    ip = get_client_ip(request)
    rate_key = f'chat_api_{ip}'
    cache.add(rate_key, 0, 3600)
    if cache.incr(rate_key) > 60:
        return JsonResponse({'error': 'Rate limit exceeded. Try again later.'}, status=429)

    try:
        data = json.loads(request.body)
        user_message = data.get('message', '').strip()
        conversation_id = data.get('conversation_id')

        if not user_message:
            return JsonResponse({'error': 'Message is required'}, status=400)

        if len(user_message) > 1000:
            return JsonResponse({'error': 'Message too long (max 1000 chars)'}, status=400)

        # Get or create conversation
        conversation = None
        if conversation_id:
            try:
                if request.user.is_authenticated:
                    conversation = Conversation.objects.get(id=conversation_id, user=request.user)
                else:
                    session_key = request.session.session_key or ''
                    conversation = Conversation.objects.get(id=conversation_id, session_key=session_key)
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

        # Get conversation history
        history = list(
            conversation.messages
            .filter(role__in=['user', 'assistant'])
            .order_by('created_at')
            .values('role', 'content')
        )

        # Save user message
        Message.objects.create(
            conversation=conversation,
            role=Message.ROLE_USER,
            content=user_message
        )

        # Call AI engine (pass user for memory personalisation)
        engine = MunicipalAIEngine()
        result = engine.chat(user_message, history, user=request.user)

        # Save assistant response
        ai_msg = Message.objects.create(
            conversation=conversation,
            role=Message.ROLE_ASSISTANT,
            content=result['response'],
            sources=result['sources'],
            intent=result['intent']
        )

        # Update conversation
        conversation.save()  # triggers updated_at
        track(request, 'chat', object_type='conversation', object_id=conversation.id)

        return JsonResponse({
            'response': result['response'],
            'conversation_id': conversation.id,
            'message_id': ai_msg.id,
            'sources': result['sources'],
            'intent': result['intent'],
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        # Dev-friendly error output (DEBUG only)
        if getattr(settings, 'DEBUG', False):
            return JsonResponse(
                {
                    'error': 'Internal server error',
                    'exception': str(e),
                },
                status=500,
            )
        return JsonResponse({'error': 'Internal server error'}, status=500)



@login_required
def chat_history(request):
    """Chat history page."""
    from django.core.paginator import Paginator
    convs = Conversation.objects.filter(
        user=request.user, is_active=True
    ).prefetch_related('messages').order_by('-updated_at')
    total_messages = Message.objects.filter(conversation__user=request.user).count()
    paginator = Paginator(convs, 15)
    page = request.GET.get('page', 1)
    conversations = paginator.get_page(page)
    # Annotate first/last message
    for conv in conversations:
        msgs = conv.messages.order_by('created_at')
        user_msgs = msgs.filter(role='user')
        conv.first_message = user_msgs.first().content[:80] if user_msgs.exists() else ''
        last = msgs.last()
        conv.last_message = last.content[:90] if last else ''
        conv.message_count = msgs.count()
    return render(request, 'chatbot/history.html', {
        'conversations': conversations,
        'total_conversations': convs.count(),
        'total_messages': total_messages,
    })


@login_required
def conversation_detail(request, pk):
    """View a specific conversation."""
    try:
        conversation = Conversation.objects.get(id=pk, user=request.user)
        messages = conversation.messages.all().order_by('created_at')
        return render(request, 'chatbot/conversation.html', {
            'conversation': conversation,
            'messages': messages
        })
    except Conversation.DoesNotExist:
        from django.http import Http404
        raise Http404


@login_required
def delete_conversation(request, pk):
    from django.http import JsonResponse
    conv = get_object_or_404(Conversation, pk=pk, user=request.user)
    if request.method == 'POST':
        conv.delete()
        return JsonResponse({'success': True})
    return JsonResponse({'success': False}, status=405)


@require_http_methods(["POST"])
def message_feedback(request):
    """Record thumbs up / down on an AI response. Level 4: feedback loop."""
    try:
        data = json.loads(request.body)
        message_id = data.get('message_id')
        rating = data.get('rating')  # 1 or -1

        if not message_id or rating not in (1, -1):
            return JsonResponse({'error': 'message_id and rating (1 or -1) required'}, status=400)

        msg = get_object_or_404(Message, pk=message_id, role=Message.ROLE_ASSISTANT)

        # Verify the caller owns the conversation containing this message.
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

        # One vote per message per user/session
        fb, created = ResponseFeedback.objects.get_or_create(
            message=msg,
            user=user,
            session_key='' if user else session_key,
            defaults={'rating': rating},
        )
        if not created:
            fb.rating = rating
            fb.save(update_fields=['rating'])

        # If negative feedback, log the original question as unanswered for admin review
        if rating == -1:
            prev = msg.conversation.messages.filter(
                role=Message.ROLE_USER,
                created_at__lt=msg.created_at
            ).order_by('-created_at').first()
            if prev:
                from chatbot.ai_engine import MunicipalAIEngine
                engine = MunicipalAIEngine()
                engine._log_unanswered(prev.content)

        return JsonResponse({'success': True, 'created': created})

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': 'Server error'}, status=500)
