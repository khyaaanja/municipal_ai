"""Server-side pending actions (§27, §48).

A write tool never executes from the model's reading of "yes". It stores a
validated payload server-side, shows the citizen what will happen, and
executes only when a later request presents the token for that stored
action. The payload is never round-tripped through the model or the
client, so it cannot be edited between review and execution.
"""
import json
import secrets

from django.core.cache import cache

TTL = 600  # ten minutes; long enough to read a summary, short enough to expire
PREFIX = 'pending_action:'

REQUESTED = 'requested'
CONSUMED = 'consumed'


class PendingError(Exception):
    """The token is unknown, expired, already used, or not the caller's."""


def owner_key(request):
    """Identity a pending action is bound to."""
    user = getattr(request, 'user', None)
    if user is not None and user.is_authenticated:
        return f'u{user.pk}'
    session = getattr(request, 'session', None)
    key = getattr(session, 'session_key', '') or ''
    return f's{key}' if key else ''


def create(request, action, payload):
    """Store a validated payload and return its single-use token."""
    owner = owner_key(request)
    if not owner:
        raise PendingError('no-identity')

    token = secrets.token_urlsafe(32)
    cache.set(
        PREFIX + token,
        json.dumps({
            'action': action,
            'payload': payload,
            'owner': owner,
            'state': REQUESTED,
        }),
        TTL,
    )
    return token


def consume(request, action, token):
    """Return the stored payload exactly once, or raise PendingError."""
    if not token:
        raise PendingError('missing-token')

    raw = cache.get(PREFIX + token)
    if raw is None:
        raise PendingError('expired-or-unknown')

    try:
        record = json.loads(raw)
    except (TypeError, ValueError):
        raise PendingError('corrupt')

    if record.get('state') != REQUESTED:
        raise PendingError('already-used')
    if record.get('action') != action:
        raise PendingError('action-mismatch')
    if not secrets.compare_digest(str(record.get('owner', '')), owner_key(request)):
        raise PendingError('not-owner')

    # Delete before executing: a crash mid-write must not leave a token that
    # could be replayed into a second complaint.
    cache.delete(PREFIX + token)
    return record['payload']
