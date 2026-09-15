from django.http import JsonResponse
from django.core.cache import cache
from django.conf import settings
from django.shortcuts import redirect
from core.utils import get_client_ip


class RateLimitMiddleware:
    """Simple IP-based rate limiting."""

    def __init__(self, get_response):
        self.get_response = get_response

    # Chat/voice/scan endpoints apply their OWN endpoint-specific rate limits
    # (in chatbot/views.py). Exempting them here prevents double-counting: the
    # homepage calls /api/chat/stream/ and, on failure, falls back to
    # /api/chat/, so enforcing the global /api/ counter would count one user
    # query 2-3 times and make users hit the cap after just a few queries.
    _CHAT_EXEMPT_PREFIXES = (
        '/api/chat/',
        '/api/voice/',
        '/api/scan/',
    )

    def __call__(self, request):
        # Only rate-limit API endpoints (skip the chat/voice/scan endpoints
        # that already enforce their own dedicated limits).
        if request.path.startswith('/api/') and not request.path.startswith(self._CHAT_EXEMPT_PREFIXES):
            ip = get_client_ip(request)
            cache_key = f'rate_limit_{ip}'
            window = getattr(settings, 'RATE_LIMIT_WINDOW', 60)
            limit = getattr(settings, 'RATE_LIMIT_REQUESTS', 60)

            # Atomic increment — immune to the read-modify-write race condition
            try:
                count = cache.incr(cache_key)
            except ValueError:
                cache.set(cache_key, 1, window)
                count = 1

            if count > limit:
                return JsonResponse(
                    {'error': 'Rate limit exceeded. Please slow down.'},
                    status=429
                )

        return self.get_response(request)


_2FA_ROLES = frozenset(('staff', 'official', 'admin', 'mayor', 'chairperson'))
_2FA_EXEMPT_PREFIXES = (
    '/2fa/', '/login/', '/logout/', '/forgot-password/',
    '/static/', '/media/', '/favicon',
)


class TwoFactorMiddleware:
    """
    Redirects privileged users who have enabled 2FA but haven't verified
    this session to the TOTP verify page.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        user = getattr(request, 'user', None)

        if (
            user and user.is_authenticated
            and getattr(user, 'otp_enabled', False)
            and user.role in _2FA_ROLES
            and not request.session.get('otp_verified')
            and not any(path.startswith(p) for p in _2FA_EXEMPT_PREFIXES)
        ):
            return redirect(f'/accounts/2fa/verify/?next={path}')

        return self.get_response(request)
