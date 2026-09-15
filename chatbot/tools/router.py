"""Deterministic intent router.

Maps a citizen's message to at most one read-only tool. Deliberately not
an LLM decision: routing by rule means a clear civic question costs no
Groq call, and the model never invents tool arguments.

Returns None whenever intent is not obvious, which hands the message back
to the normal answering path rather than guessing at a tool.
"""
import re

COMPLAINT_REF = re.compile(r'\b(BK-[A-Z0-9]{6})\b')

# Nepali and romanised-Nepali forms sit alongside English: "mero" (my),
# "gunaso" (complaint), "sifaris" (recommendation/application).
_MINE = ('my ', 'mero ', 'mera ', 'i have', 'show me my')

_ROUTES = [
    ('get_my_complaints', (
        'my complaint', 'my complaints', 'mero gunaso', 'mero ujuri',
        'my reports', 'my issues', 'complaints i filed',
    )),
    ('get_my_service_requests', (
        'my application', 'my applications', 'my service request',
        'mero nivedan', 'my requests', 'application status',
    )),
    ('get_my_proposals', (
        'my proposal', 'my proposals', 'mero prastav', 'proposals i submitted',
    )),
    ('get_my_notifications', (
        'my notification', 'notifications', 'any updates for me', 'my alerts',
    )),
    ('list_events', (
        'what events', 'upcoming events', 'events this', 'festival',
        'jatra', 'what is happening', "what's happening", 'events near',
    )),
    ('list_public_notices', (
        'public notice', 'notices', 'tender', 'vacancy', 'job opening',
        'suchana',
    )),
    ('find_businesses', (
        'restaurant', 'where can i eat', 'hotel', 'shop', 'cafe',
        'khaja', 'food near',
    )),
    ('mark_notifications_read', (
        'mark notifications read', 'mark all read', 'clear my notifications',
    )),
    ('find_on_map', (
        'where is', 'show me on the map', 'on the map', 'directions to',
        'how do i get to', 'location of',
    )),
    ('find_attractions', (
        'temple', 'heritage', 'museum', 'what to see', 'tourist',
        'durbar square', 'attraction', 'mandir',
    )),
]


def route(message, claim_token=''):
    """Return (tool_name, kwargs) or None when intent is not obvious."""
    if not message or not isinstance(message, str):
        return None

    text = message.strip()
    lowered = text.lower()

    ref = COMPLAINT_REF.search(text.upper())
    if ref:
        return 'get_complaint_status', {
            'complaint_id': ref.group(1),
            'claim_token': claim_token,
        }

    for name, phrases in _ROUTES:
        if any(p in lowered for p in phrases):
            if (name.startswith('get_my_') or name == 'mark_notifications_read') \
                    and not any(m in lowered for m in _MINE):
                # "notifications" alone is ambiguous; "my notifications" is not.
                continue
            return name, _kwargs_for(name, lowered)

    return None


def _kwargs_for(name, lowered):
    if name == 'get_my_notifications':
        return {'unread_only': 'unread' in lowered}
    if name in ('find_businesses', 'find_attractions'):
        return {}
    return {}
