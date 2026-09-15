import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'municipal_ai.settings')

app = Celery('municipal_ai')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# ── Periodic tasks (django-celery-beat manages schedule in DB) ──────────────
app.conf.beat_schedule = {
    # Embed KB entries that have no vectors yet — runs every 5 minutes
    'embed-pending-kb-entries': {
        'task': 'chatbot.tasks.embed_pending_kb_entries',
        'schedule': crontab(minute='*/5'),
    },
    # Clean up auto-generated KB entries older than 30 days with low priority
    'prune-stale-auto-kb': {
        'task': 'chatbot.tasks.prune_stale_auto_kb',
        'schedule': crontab(hour=3, minute=0),  # daily at 3AM Kathmandu time
    },
}
