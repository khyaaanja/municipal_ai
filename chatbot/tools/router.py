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
_MINE = ('my ', 'mero ', 'mera ', 'i have', 'show me my', 'मेरो', 'मेरा')

_ROUTES = [
    ('get_my_complaints', (
        'my complaint', 'my complaints', 'mero gunaso', 'mero ujuri',
        'मेरो गुनासो', 'मेरा गुनासो', 'मेरो उजुरी',
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
        'happening today', 'happening tomorrow', 'on today', 'events today',
        'events',  # bare, so Nepali phrasing like 'आज के events छ' still routes
        'कार्यक्रम', 'जात्रा', 'चाडपर्व',
    )),
    ('list_public_notices', (
        'public notice', 'notices', 'tender', 'vacancy', 'job opening',
        'suchana', 'सूचना', 'बोलपत्र', 'टेन्डर', 'सूचनाहरू',
    )),
    ('find_businesses', (
        'restaurant', 'where can i eat', 'hotel', 'shop', 'cafe',
        'khaja', 'food near',
        'रेस्टुरेन्ट', 'खाना', 'होटल', 'पसल',
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
        # "what to see" did not cover the way visitors actually phrase it:
        # "what is there to see" matched no route and no knowledge, so the
        # commonest opening question of all fell through to nothing.
        'there to see', 'things to do', 'what to do', 'worth visiting',
        'मन्दिर', 'दरबार', 'सम्पदा', 'घुम्न', 'हेर्न',
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
            if name == 'find_on_map' and not _place_from(lowered):
                # No place named — let knowledge or the model answer instead
                # of replying "that looks empty".
                continue
            if (name.startswith('get_my_') or name == 'mark_notifications_read') \
                    and not any(m in lowered for m in _MINE):
                # "notifications" alone is ambiguous; "my notifications" is not.
                continue
            return name, _kwargs_for(name, lowered)

    return None


def _when_from(lowered):
    if 'today' in lowered or 'tonight' in lowered or 'आज' in lowered:
        return 'today'
    if 'tomorrow' in lowered or 'भोलि' in lowered:
        return 'tomorrow'
    if 'this week' in lowered or 'this weekend' in lowered:
        return 'week'
    return 'upcoming'


PLACE_AFTER = re.compile(
    r'(?:where is|location of|directions to|how do i get to|on the map|show me on the map)\s+'
    r'(?:the\s+)?([a-z\u0900-\u097F][\w\s\u0900-\u097F]{2,40})')


def _place_from(lowered):
    """The place name a map lookup needs, or '' when the question names none."""
    match = PLACE_AFTER.search(lowered)
    if not match:
        return ''
    # Trim a trailing clause: "get to Bhaktapur from Kathmandu" asks about
    # Bhaktapur, and "from Kathmandu" is not part of the place name.
    place = re.split(r'\b(?:from|by|in|near|at|via)\b', match.group(1))[0]
    return place.strip(' ?.!,')


def _kwargs_for(name, lowered):
    if name == 'list_events':
        return {'when': _when_from(lowered)}
    if name == 'find_on_map':
        return {'query': _place_from(lowered)}
    if name == 'get_my_notifications':
        return {'unread_only': 'unread' in lowered}
    if name in ('find_businesses', 'find_attractions'):
        return {}
    return {}
