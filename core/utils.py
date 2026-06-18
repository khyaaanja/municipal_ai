from django.core.cache import cache


def get_client_ip(request):
    """Extract real client IP, honouring X-Forwarded-For from trusted proxies."""
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', '0.0.0.0')


def increment_rate_counter(key: str, ttl: int) -> int:
    """Atomically increment a cache counter. Returns the new count."""
    cache.add(key, 0, ttl)
    return cache.incr(key)
