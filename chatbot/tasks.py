from celery import shared_task
import logging
import json

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=1, default_retry_delay=5, time_limit=90, soft_time_limit=80)
def process_chat_async(self, job_id: str, user_message: str, history: list,
                       user_id=None, conversation_id=None, session_key=None,
                       is_staff=False, claim_token=None):
    """
    Async Celery task for AI chat.  Queued by chat_async view, polled via chat_poll.
    Result stored in Redis under key  chat_job:<job_id>  with a 1-hour TTL.
    """
    from django.core.cache import cache
    from django.conf import settings

    def _set(payload: dict):
        cache.set(f'chat_job:{job_id}', json.dumps(payload), 3600)

    _set({'status': 'processing'})

    try:
        # Fast-path: complaint ID lookup (no Groq needed)
        import re as _re
        _cid = _re.search(r'\b(BK-[A-Z0-9]{6,10})\b', user_message.upper())
        if _cid:
            try:
                from complaints.models import Complaint as _C
                c = _C.objects.get(complaint_id=_cid.group(1))
                if is_staff:
                    can_view = True
                elif user_id:
                    can_view = c.user_id == user_id
                else:
                    can_view = bool(
                        (session_key and c.user_id is None and c.session_key == session_key)
                        or (claim_token and c.claim_token and str(c.claim_token) == str(claim_token))
                    )
                if not can_view:
                    _set({
                        'status': 'done',
                        'response': (
                            "For privacy, complaint details are only available to the "
                            "complainant. Sign in, use the claim link from your confirmation, "
                            "or visit the public tracking page."
                        ),
                        'sources': [],
                        'intent': 'complaint_status',
                        'followups': [],
                        'conversation_id': conversation_id,
                        'message_id': None,
                    })
                    return
                status_text = dict(_C.STATUS_CHOICES).get(c.status, c.status)
                reply = (
                    f"**Complaint {c.complaint_id}** found!\n\n"
                    f"**Status:** {status_text}\n"
                    f"**Category:** {c.get_category_display()}\n"
                    f"**Title:** {c.title}\n"
                    f"**Filed:** {c.created_at.strftime('%b %d, %Y')}"
                )
                _set({'status': 'done', 'response': reply, 'sources': [], 'intent': 'complaint_status',
                      'followups': [], 'conversation_id': conversation_id, 'message_id': None,
                      'source': 'complaint_lookup', 'source_note': None, 'fallback': False,
                      'degraded': False, 'citations': []})
                return
            except Exception:
                pass

        # Full AI engine path
        from chatbot.ai_engine import MunicipalAIEngine
        engine = MunicipalAIEngine()

        user_obj = None
        if user_id:
            try:
                from django.contrib.auth import get_user_model
                user_obj = get_user_model().objects.get(pk=user_id)
            except Exception:
                pass

        result = engine.chat(user_message, history, user=user_obj)
        try:
            from chatbot.services.answer_engine import is_degraded_response
            if result.get('response', '').strip() and (
                result.get('degraded')
                or result.get('fallback')
                or is_degraded_response(result.get('response', ''))
            ):
                from chatbot.views import _answer_with_fallback
                fallback_result = _answer_with_fallback(
                    None, user_message, history, user=user_obj
                )
                if fallback_result and fallback_result.get('answer'):
                    metadata = fallback_result.get('metadata', {})
                    result.update({
                        'response': fallback_result['answer'],
                        'source': fallback_result.get('source', 'local_db'),
                        'sources': metadata.get('sources', ['knowledge_base']),
                        'source_note': metadata.get('source_note') or 'Answered from local records',
                        'fallback': True,
                        'degraded': True,
                        'citations': metadata.get('citations', []),
                    })
        except Exception:
            logger.exception('chat_async: fallback coordination failed')

        # Persist message to DB
        msg_id = None
        conv_id = conversation_id
        try:
            from chatbot.models import Conversation, Message
            if conv_id:
                if user_id:
                    conversation = Conversation.objects.get(pk=conv_id, user_id=user_id)
                else:
                    conversation = Conversation.objects.get(
                        pk=conv_id,
                        user__isnull=True,
                        session_key=session_key or '',
                    )
            else:
                conversation = Conversation.objects.create(
                    user=user_obj,
                    session_key=session_key,
                    title=user_message[:50],
                )
                conv_id = conversation.pk

            Message.objects.create(conversation=conversation, role=Message.ROLE_USER, content=user_message)
            if result.get('response', '').strip():
                ai_msg = Message.objects.create(
                    conversation=conversation,
                    role=Message.ROLE_ASSISTANT,
                    content=result['response'],
                    sources=result.get('sources', []),
                    intent=result.get('intent', ''),
                )
                msg_id = ai_msg.pk
            conversation.save()
        except Exception as db_exc:
            logger.warning('chat_async: DB persist failed: %s', db_exc)

        _set({
            'status': 'done',
            'response': result['response'],
            'sources': result.get('sources', []),
            'intent': result.get('intent', ''),
            'followups': result.get('followups', []),
            'conversation_id': conv_id,
            'message_id': msg_id,
            'source': result.get('source'),
            'source_note': result.get('source_note'),
            'fallback': result.get('fallback', False),
            'degraded': result.get('degraded', False),
            'citations': result.get('citations', []),
        })

        # Auto-save interesting answers to KB asynchronously
        try:
            auto_save_kb_entry.delay(user_message, result['response'], result.get('intent', ''))
        except Exception as enqueue_exc:
            # Autosave is secondary; never turn a completed answer into a job error.
            logger.warning('chat_async: KB autosave enqueue failed: %s', enqueue_exc)

    except Exception as exc:
        logger.exception('process_chat_async job %s failed: %s', job_id, exc)
        _set({'status': 'error', 'error': 'AI is temporarily unavailable. Please try again.'})


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def embed_pending_kb_entries(self):
    """
    Embed up to 10 KnowledgeBase entries that have no vector yet.
    Runs every 5 minutes via Celery Beat — off the hot chat path.
    """
    try:
        from django.conf import settings
        from chatbot.models import KnowledgeBase
        from chatbot.ai_engine import MunicipalAIEngine

        api_key = getattr(settings, 'GROQ_API_KEY', '')
        if not api_key:
            return {'status': 'skip', 'reason': 'no api key'}

        engine = MunicipalAIEngine()
        pending = list(KnowledgeBase.objects.filter(is_active=True, embedding__isnull=True)[:10])
        embedded = 0
        for entry in pending:
            vec = engine._embed(f"{entry.title}: {entry.content[:800]}")
            if vec:
                KnowledgeBase.objects.filter(pk=entry.pk).update(embedding=vec)
                embedded += 1
        return {'status': 'ok', 'embedded': embedded}
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task(bind=True, max_retries=1, default_retry_delay=60)
def auto_save_kb_entry(self, query: str, response: str, intent: str):
    """
    Save a useful AI response to the KB asynchronously after the chat response
    has already been sent to the user. Decoupled from the request cycle.
    """
    try:
        from chatbot.ai_engine import MunicipalAIEngine
        engine = MunicipalAIEngine()
        engine._maybe_auto_save_kb(query, response, intent)
        return {'status': 'ok'}
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task
def prune_stale_auto_kb():
    """
    Remove auto-generated KB entries older than 30 days that were never
    promoted (still at priority -1). Keeps the KB clean.
    """
    from django.utils import timezone
    from datetime import timedelta
    from chatbot.models import KnowledgeBase

    cutoff = timezone.now() - timedelta(days=30)
    deleted, _ = KnowledgeBase.objects.filter(
        auto_generated=True,
        priority=-1,
        created_at__lt=cutoff,
    ).delete()
    return {'status': 'ok', 'pruned': deleted}


@shared_task
def send_complaint_notification_async(complaint_log_id: int):
    """
    Send a complaint status-change email asynchronously.
    Called by the post_save signal instead of doing it synchronously.
    """
    try:
        from dashboard.models import ComplaintLog
        from django.core.mail import send_mail
        from django.conf import settings

        log = ComplaintLog.objects.select_related('complaint', 'complaint__user').get(pk=complaint_log_id)
        complaint = log.complaint

        recipients = []
        if complaint.submitter_email:
            recipients.append(complaint.submitter_email)
        if complaint.user and complaint.user.email and complaint.user.email not in recipients:
            recipients.append(complaint.user.email)
        if not recipients:
            return {'status': 'skip', 'reason': 'no recipients'}

        status_labels = {
            'PENDING': 'Pending Review', 'IN_REVIEW': 'In Review',
            'IN_PROGRESS': 'In Progress', 'RESOLVED': 'Resolved ✓', 'REJECTED': 'Rejected',
        }
        old_label = status_labels.get(log.old_status, log.old_status)
        new_label = status_labels.get(log.new_status, log.new_status)
        name = complaint.submitter_name or 'Citizen'
        note_section = f"\nStaff Note:\n{log.note}\n" if log.note else ''
        site_url = getattr(settings, 'SITE_URL', 'http://localhost:8000')

        send_mail(
            subject=f"[{complaint.complaint_id}] Status Update: {new_label}",
            message=(
                f"Dear {name},\n\n"
                f"Your complaint has been updated.\n\n"
                f"Complaint ID : {complaint.complaint_id}\n"
                f"Title        : {complaint.title}\n"
                f"Status       : {old_label} → {new_label}\n"
                f"{note_section}\n"
                f"Track your complaint:\n"
                f"{site_url}/complaint/track/?id={complaint.complaint_id}\n\n"
                f"Bhaktapur Municipal AI Platform\n"
                f"Municipality Office: +977-1-6610000"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            fail_silently=True,
        )
        return {'status': 'ok', 'recipients': len(recipients)}
    except ComplaintLog.DoesNotExist:
        return {'status': 'skip', 'reason': 'log not found'}
    except Exception as exc:
        return {'status': 'error', 'error': str(exc)}


@shared_task
def warm_context_cache():
    """
    Pre-populate Redis with attraction/event/restaurant data so the first
    request after cache expiry doesn't pay the DB hit. Runs every 8 minutes.
    """
    try:
        from chatbot.ai_engine import CityContextRetriever
        r = CityContextRetriever()
        r._get_attractions()
        r._get_events()
        r._get_restaurants()
        r._get_hotels()
        r._get_products()
        r._get_news()
        for cat in ['heritage', 'culture', 'transport', 'emergency', 'services', 'rules', 'general']:
            r._get_kb(cat)
        logger.info("warm_context_cache: cache refreshed")
        return {'status': 'ok'}
    except Exception as exc:
        logger.exception("warm_context_cache failed: %s", exc)
        return {'status': 'error', 'error': str(exc)}


@shared_task
def embed_new_kb_entries_batch():
    """
    Embed all KB entries that don't have vectors yet, in batches of 20.
    Runs every 10 minutes via Celery Beat. More aggressive than the inline
    opportunistic embedder — ensures new admin-created entries are vectorized quickly.
    """
    try:
        from django.conf import settings as _settings
        from chatbot.models import KnowledgeBase
        from chatbot.ai_engine import MunicipalAIEngine, _get_groq_client

        api_key = getattr(_settings, 'GROQ_API_KEY', '')
        if not api_key:
            return {'status': 'skip', 'reason': 'no api key'}

        engine  = MunicipalAIEngine()
        pending = list(KnowledgeBase.objects.filter(is_active=True, embedding__isnull=True)[:20])
        embedded = 0
        for entry in pending:
            vec = engine._embed(f"{entry.title}: {entry.content[:800]}")
            if vec:
                KnowledgeBase.objects.filter(pk=entry.pk).update(embedding=vec)
                embedded += 1
        logger.info("embed_new_kb_entries_batch: embedded %d entries", embedded)
        return {'status': 'ok', 'embedded': embedded, 'remaining': max(0, len(pending) - embedded)}
    except Exception as exc:
        logger.exception("embed_new_kb_entries_batch failed: %s", exc)
        return {'status': 'error', 'error': str(exc)}


@shared_task
def sync_municipal_announcements():
    """
    Pull fresh announcements and news from the municipality's own DB
    into KB auto-entries so the AI always has up-to-date civic news.
    Runs every 6 hours via Celery Beat.
    """
    try:
        from django.utils import timezone as _tz
        from chatbot.models import KnowledgeBase
        from news.models import NewsArticle

        created_count = 0
        cutoff = _tz.now() - __import__('datetime').timedelta(days=7)
        recent_news = NewsArticle.objects.filter(
            is_active=True, published_at__gte=cutoff
        ).order_by('-published_at')[:20]

        for article in recent_news:
            title = f"[News] {article.title}"
            if KnowledgeBase.objects.filter(title=title).exists():
                continue
            content = f"{article.summary or ''}\n\n{article.content[:600] if hasattr(article, 'content') else ''}".strip()
            if not content:
                continue
            KnowledgeBase.objects.create(
                title=title,
                content=content,
                category='general',
                keywords=article.title[:400],
                auto_generated=True,
                priority=0,
            )
            created_count += 1

        logger.info("sync_municipal_announcements: created %d KB entries", created_count)
        return {'status': 'ok', 'created': created_count}
    except Exception as exc:
        logger.exception("sync_municipal_announcements failed: %s", exc)
        return {'status': 'error', 'error': str(exc)}


@shared_task(bind=True, max_retries=1, time_limit=60, soft_time_limit=50)
def categorize_complaint_async(self, complaint_pk: int):
    """
    Run AI categorization on a newly submitted complaint without blocking
    the HTTP response. Dispatched by complaints/views.py after saving.
    Falls back to no-op if Groq is unavailable.
    """
    try:
        from complaints.models import Complaint
        from chatbot.ai_engine import MunicipalAIEngine

        try:
            complaint = Complaint.objects.get(pk=complaint_pk)
        except Complaint.DoesNotExist:
            return {'status': 'skip', 'reason': 'complaint not found'}

        engine = MunicipalAIEngine()
        ai_cat = engine.categorize_complaint(complaint.title, complaint.description)

        update_fields = []
        if ai_cat.get('category'):
            from complaints.models import Complaint as _C
            valid_cats = {c[0] for c in _C.CATEGORY_CHOICES}
            if ai_cat['category'] in valid_cats and complaint.category == 'OTHER':
                complaint.category = ai_cat['category']
                update_fields.append('category')

        if ai_cat.get('priority'):
            pmap = {'low': 'LOW', 'medium': 'MEDIUM', 'high': 'HIGH', 'urgent': 'CRITICAL'}
            mapped = pmap.get(ai_cat['priority'].lower())
            if mapped and complaint.priority == 'MEDIUM':
                complaint.priority = mapped
                update_fields.append('priority')

        if ai_cat.get('ward') and not complaint.ward_number:
            w = ai_cat['ward']
            if isinstance(w, int) and 1 <= w <= 17:
                complaint.ward_number = w
                update_fields.append('ward_number')

        if update_fields:
            complaint.save(update_fields=update_fields)
            logger.info(
                "categorize_complaint_async: updated complaint %s fields=%s",
                complaint.complaint_id, update_fields,
            )

        return {'status': 'ok', 'updated': update_fields}
    except Exception as exc:
        logger.warning("categorize_complaint_async failed for pk=%s: %s", complaint_pk, exc)
        return {'status': 'error', 'error': str(exc)}
