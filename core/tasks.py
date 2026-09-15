"""
Celery tasks for core app — cache warming and periodic maintenance.
"""
from celery import shared_task
from django.core.cache import cache


@shared_task
def warm_homepage_cache():
    """Pre-warm homepage context cache every 10 minutes, so first visitors
    after cache expiry never experience a cold-start lag spike."""
    from core.views import build_homepage_context, _HOMEPAGE_CACHE_KEY, _HOMEPAGE_TTL
    ctx = build_homepage_context()
    cache.set(_HOMEPAGE_CACHE_KEY, ctx, _HOMEPAGE_TTL)
    return f"Homepage cache warmed ({len(ctx)} keys), TTL={_HOMEPAGE_TTL}s"

