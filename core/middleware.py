from django.http import JsonResponse
from django.core.cache import cache
from django.conf import settings
from core.utils import get_client_ip
import time


class RateLimitMiddleware:
    """Simple IP-based rate limiting."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Only rate-limit API endpoints
        if request.path.startswith('/api/'):
            ip = get_client_ip(request)
            cache_key = f'rate_limit_{ip}'
            requests = cache.get(cache_key, [])
            now = time.time()
            window = getattr(settings, 'RATE_LIMIT_WINDOW', 60)
            limit = getattr(settings, 'RATE_LIMIT_REQUESTS', 60)

            # Filter to current window
            requests = [r for r in requests if now - r < window]

            if len(requests) >= limit:
                return JsonResponse(
                    {'error': 'Rate limit exceeded. Please slow down.'},
                    status=429
                )

            requests.append(now)
            cache.set(cache_key, requests, window)

        return self.get_response(request)

