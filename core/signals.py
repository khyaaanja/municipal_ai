"""
Cache invalidation signals.
When any content model is saved/deleted, bust the relevant cached list pages
so users never see stale data longer than the cache TTL.
"""
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.core.cache import cache


def _bust(*keys):
    cache.delete_many(keys)


# ── Homepage ──────────────────────────────────────────────────────────────────
def _bust_homepage(**_):
    cache.delete('homepage_ctx')


# ── Attractions ───────────────────────────────────────────────────────────────
def _bust_attractions(**_):
    _bust('attractions_list:all')
    cache.delete_pattern('attractions_list:*') if hasattr(cache, 'delete_pattern') else None
    # fallback: manual key bust for common categories
    for cat in ['temples', 'museums', 'squares', 'parks', 'heritage', '']:
        cache.delete(f'attractions_list:{cat or "all"}')


# ── Events ────────────────────────────────────────────────────────────────────
def _bust_events(**_):
    for w in ['upcoming', 'today', 'this_week', 'past']:
        cache.delete(f'events_list:{w}')


# ── News ──────────────────────────────────────────────────────────────────────
def _bust_news(**_):
    cache.delete('news_list:page1')


# ── Businesses ────────────────────────────────────────────────────────────────
def _bust_businesses(**_):
    for cat in ['accommodation', 'restaurant', 'shop', 'transport', 'tour_guide', 'other', 'all']:
        cache.delete(f'businesses_list:{cat}')


# ── Marketplace ───────────────────────────────────────────────────────────────
def _bust_marketplace(**_):
    cache.delete('marketplace_list:all')
    for cat in ['pottery', 'thangka', 'woodcraft', 'metalwork', 'textiles', '']:
        cache.delete(f'marketplace_list:{cat or "all"}')


def connect_signals():
    """Wire up all cache-busting signals. Called from AppConfig.ready()."""
    try:
        from tourism.models import Attraction
        post_save.connect(_bust_attractions, sender=Attraction)
        post_delete.connect(_bust_attractions, sender=Attraction)
        _bust_homepage_on = _bust_homepage
        post_save.connect(_bust_homepage_on, sender=Attraction)
    except Exception:
        pass

    try:
        from events.models import Event
        post_save.connect(_bust_events, sender=Event)
        post_delete.connect(_bust_events, sender=Event)
        post_save.connect(_bust_homepage, sender=Event)
    except Exception:
        pass

    try:
        from news.models import NewsArticle
        post_save.connect(_bust_news, sender=NewsArticle)
        post_delete.connect(_bust_news, sender=NewsArticle)
        post_save.connect(_bust_homepage, sender=NewsArticle)
    except Exception:
        pass

    try:
        from businesses.models import Business
        post_save.connect(_bust_businesses, sender=Business)
        post_delete.connect(_bust_businesses, sender=Business)
        post_save.connect(_bust_homepage, sender=Business)
    except Exception:
        pass

    try:
        from marketplace.models import Product
        post_save.connect(_bust_marketplace, sender=Product)
        post_delete.connect(_bust_marketplace, sender=Product)
    except Exception:
        pass
