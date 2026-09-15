# Load Celery app so @shared_task works across all Django apps
from .celery import app as celery_app

__all__ = ('celery_app',)
