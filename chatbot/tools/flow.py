"""Conversation flow for tool-backed replies.

Holds the small amount of state a filing conversation needs, entirely in
the Django session. Nothing about a pending complaint is ever echoed to
the client or passed through the model: the browser sees a summary, the
server keeps the payload.
"""
import re

from .base import run_tool
from .present import present
from .router import COMPLAINT_REF, route

PENDING_KEY = 'pending_complaint_token'
SLOTS_KEY = 'complaint_slots'
PENDING_TOOL_KEY = 'pending_confirm_tool'

AFFIRMATIVE = {
    'yes', 'y', 'yeah', 'yep', 'ok', 'okay', 'confirm', 'confirmed',
    'file it', 'submit', 'submit it', 'yes please', 'go ahead', 'send it',
    'yes file it', 'do it',
    'ho', 'huncha', 'thik cha', 'thik', 'pathau',      # Nepali
}
NEGATIVE = {'no', 'n', 'nope', 'cancel', 'stop', 'never mind', 'nevermind', 'chaina'}

CIVIC_KEYWORDS = {
    'ROAD': ('pothole', 'broken road', 'road damage', 'bad road', 'road repair',
             'sadak'),
    'SANITATION': ('garbage', 'trash', 'waste', 'litter', 'dirty street',
                   'rubbish', 'fohor'),
    'WATER': ('water leak', 'no water', 'water cut', 'dirty water', 'water pipe',
              'water supply', 'pani'),
    'ELECTRICITY': ('power cut', 'no electricity', 'blackout', 'power failure',
                    'streetlight', 'street light', 'batti'),
    'NOISE': ('loud noise', 'noise pollution', 'noisy'),
    'INFRASTRUCTURE': ('broken bridge', 'drainage', 'sewer', 'blocked drain',
                       'footpath', 'pavement'),
}

REPORT_INTENT = ('report a', 'report the', 'complain', 'file a', 'there is a',
                 'there is', 'broken', 'gunaso', 'ujuri')



def _has_report_intent(lowered):
    """Word-boundary match.

    Both ends matter. A leading boundary alone still let "complain" fire on
    "list every complaint with phone numbers" — a request for data, not a
    report — because "complaints" starts with "complain".
    """
    return any(re.search(rf'\b{re.escape(phrase)}\b', lowered)
               for phrase in REPORT_INTENT)


def _normalise(message):
    return (message or '').strip().lower().rstrip('.!?')


def detect_category(lowered):
    for category, words in CIVIC_KEYWORDS.items():
        if any(w in lowered for w in words):
            return category
    return None


def handle(request, message, claim_token=''):
    """Return (reply, followups, intent) or None to fall through to the LLM."""
    session = getattr(request, 'session', None)
    if session is None:
        return _routed_only(request, message, claim_token)

    lowered = _normalise(message)

    pending = session.get(PENDING_KEY)
    if pending:
        confirm_tool = session.get(PENDING_TOOL_KEY, 'confirm_complaint')
        if lowered in AFFIRMATIVE:
            result = run_tool(confirm_tool, request, token=pending)
            session.pop(PENDING_KEY, None)
            session.pop(PENDING_TOOL_KEY, None)
            session.pop(SLOTS_KEY, None)
            return _with_intent(present(confirm_tool, result), confirm_tool)
        if lowered in NEGATIVE:
            session.pop(PENDING_KEY, None)
            session.pop(PENDING_TOOL_KEY, None)
            session.pop(SLOTS_KEY, None)
            return ('Nothing was submitted. Tell me if you want to start again.',
                    [], 'submission_cancelled')
        # Anything else is treated as a correction, so a half-finished draft
        # is never silently submitted by an ambiguous reply.
        session.pop(PENDING_KEY, None)
        session.pop(PENDING_TOOL_KEY, None)
        return ('Nothing has been submitted. Tell me again and I will '
                'prepare a fresh draft.', [], 'submission_cancelled')

    # An explicit reference is unambiguous and always wins.
    if COMPLAINT_REF.search(message.upper()):
        routed = route(message, claim_token=claim_token)
        if routed:
            name, kwargs = routed
            return _with_intent(present(name, run_tool(name, request, **kwargs)),
                                name)

    # A filing conversation in progress owns the next message. Routing on
    # keywords here would read "Durbar Square road" as a sightseeing query
    # and silently drop the answer to the question just asked.
    in_progress = bool(session.get(SLOTS_KEY))

    # Reporting a problem outranks a topic keyword. "garbage piling up near
    # the temple" is a sanitation complaint, not a request for temple
    # opening hours, and routing on 'temple' would lose the report.
    reporting = detect_category(lowered) or _has_report_intent(lowered)

    if not in_progress:
        routed = route(message, claim_token=claim_token)
        if routed:
            name, kwargs = routed
            # A get_* match is an explicit personal lookup ("my complaints")
            # and wins outright. The rest are broad topic matches, which yield
            # to a report so a complaint is never answered with sightseeing.
            if name.startswith('get_') or not reporting:
                return _with_intent(
                    present(name, run_tool(name, request, **kwargs)), name)

    handled = _filing_flow(request, session, message, lowered)
    if handled is not None:
        return handled

    # Retrieval before the model: if the municipality has a verified answer,
    # use it rather than paying for a generated one (sections 42-43). A weak
    # match falls through, so the assistant never presents a poor retrieval
    # hit as though it were an answer.
    return _knowledge_fallback(request, message)


def _knowledge_fallback(request, message):
    result = run_tool('search_municipal_knowledge', request, query=message)
    if not result.ok or not result.data.get('found'):
        return None
    if result.data.get('confidence') in (None, 'none', 'low'):
        return None
    return _with_intent(present('search_municipal_knowledge', result),
                        'search_municipal_knowledge')


def _with_intent(presented, intent):
    reply, followups = presented
    return reply, followups, intent


def _routed_only(request, message, claim_token):
    routed = route(message, claim_token=claim_token)
    if not routed:
        return None
    name, kwargs = routed
    return _with_intent(present(name, run_tool(name, request, **kwargs)), name)


def _filing_flow(request, session, message, lowered):
    slots = dict(session.get(SLOTS_KEY) or {})
    started = bool(slots)

    if not started:
        category = detect_category(lowered)
        wants_to_report = _has_report_intent(lowered)
        if not category and not wants_to_report:
            return None
        if not category:
            return ('I can file that for you. What kind of issue is it — '
                    'roads, sanitation, water, electricity, noise or '
                    'infrastructure?', [], 'complaint_filing')
        slots = {'category': category, 'description': message.strip()}
        session[SLOTS_KEY] = slots
        return (f"I can file a **{category.title()}** complaint about that. "
                'Where is it? A landmark or street name is enough.',
                [], 'complaint_filing')

    if not slots.get('category'):
        category = detect_category(lowered)
        if not category:
            return ('I still need the category — roads, sanitation, water, '
                    'electricity, noise or infrastructure?', [], 'complaint_filing')
        slots['category'] = category
        session[SLOTS_KEY] = slots
        return ('Got it. Where is the problem?', [], 'complaint_filing')

    if not slots.get('location'):
        slots['location'] = message.strip()
        session[SLOTS_KEY] = slots

    if not request.user.is_authenticated and not slots.get('submitter_name'):
        if slots.get('location') and slots.get('_asked_name'):
            slots['submitter_name'] = message.strip()
            session[SLOTS_KEY] = slots
        else:
            slots['_asked_name'] = True
            session[SLOTS_KEY] = slots
            return ('And what name should I file it under?', [], 'complaint_filing')

    result = run_tool(
        'draft_complaint', request,
        category=slots['category'],
        title=slots['description'][:80],
        description=slots['description'],
        location=slots['location'],
        submitter_name=slots.get('submitter_name', ''),
    )
    if result.ok:
        session[PENDING_KEY] = result.data['token']
        session[PENDING_TOOL_KEY] = 'confirm_complaint'
    session.pop(SLOTS_KEY, None)
    return _with_intent(present('draft_complaint', result), 'draft_complaint')
