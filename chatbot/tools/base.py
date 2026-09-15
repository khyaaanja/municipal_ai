"""Least-privilege tool contract.

Every tool declares its auth requirement, rate limits and cacheability up
front. The dispatcher enforces all three before the tool body runs, so a
tool cannot accidentally be reached without its controls.
"""
import logging
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable, Optional

from core.utils import get_client_ip, increment_rate_counter

audit_log = logging.getLogger('municipal_ai.audit')
error_log = logging.getLogger('municipal_ai.tools')

AUTH_NONE = 'none'
AUTH_OPTIONAL = 'optional'
AUTH_REQUIRED = 'required'

RATE_WINDOW = 3600

SIGN_IN_REQUIRED = 'You need to be signed in for that. Would you like to log in?'
RATE_EXCEEDED = "You've made a lot of requests recently. Please try again in a little while."
UNAVAILABLE = "I couldn't complete that request right now."

REGISTRY: dict[str, 'ToolSpec'] = {}


class ToolInputError(Exception):
    """Validation failure safe to show the citizen."""


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    data: Any = None
    error: Optional[str] = None
    # Results derived from a specific user's records must never reach the
    # shared ai_resp_ cache, which is keyed on message text alone.
    cacheable: bool = False


@dataclass(frozen=True)
class ToolSpec:
    name: str
    auth: str
    rate_user: int
    rate_ip: int
    audit: bool
    cacheable: bool
    run: Callable


def _denied(message: str) -> ToolResult:
    return ToolResult(ok=False, error=message, cacheable=False)


def tool(name, *, auth=AUTH_NONE, rate_user=0, rate_ip=0, audit=False, cacheable=False):
    if cacheable and auth == AUTH_REQUIRED:
        raise ValueError(f'{name}: per-user results are never cacheable')

    def decorator(fn):
        @wraps(fn)
        def run(request, **kwargs) -> ToolResult:
            user = getattr(request, 'user', None)
            authed = bool(user and user.is_authenticated)

            if auth == AUTH_REQUIRED and not authed:
                _record(name, request, 'denied_unauthenticated', audit)
                return _denied(SIGN_IN_REQUIRED)

            if rate_user and authed:
                if increment_rate_counter(f'tool:{name}:u{user.pk}', RATE_WINDOW) > rate_user:
                    _record(name, request, 'rate_limited_user', audit)
                    return _denied(RATE_EXCEEDED)

            if rate_ip:
                ip = get_client_ip(request)
                if increment_rate_counter(f'tool:{name}:i{ip}', RATE_WINDOW) > rate_ip:
                    _record(name, request, 'rate_limited_ip', audit)
                    return _denied(RATE_EXCEEDED)

            try:
                data = fn(request, **kwargs)
            except ToolInputError as exc:
                _record(name, request, 'invalid_input', audit)
                return _denied(str(exc))
            except Exception:
                # Internals stay server-side; the citizen gets a plain statement.
                error_log.exception('tool %s failed', name)
                _record(name, request, 'error', audit)
                return _denied(UNAVAILABLE)

            _record(name, request, 'ok', audit)
            return ToolResult(ok=True, data=data, cacheable=cacheable)

        REGISTRY[name] = ToolSpec(
            name=name, auth=auth, rate_user=rate_user, rate_ip=rate_ip,
            audit=audit, cacheable=cacheable, run=run,
        )
        return run
    return decorator


def _record(name, request, outcome, audit):
    if not audit:
        return
    user = getattr(request, 'user', None)
    uid = user.pk if user and user.is_authenticated else None
    audit_log.info(
        'tool=%s outcome=%s user=%s ip=%s',
        name, outcome, uid, get_client_ip(request),
    )


def run_tool(name, request, **kwargs) -> ToolResult:
    spec = REGISTRY.get(name)
    if spec is None:
        return _denied(UNAVAILABLE)
    return spec.run(request, **kwargs)
