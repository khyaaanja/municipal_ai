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

# Devanagari was missing here for the same reason it was missing from
# CIVIC_KEYWORDS: the romanised forms were added and the script the
# municipality actually publishes in was not. It matters more here, because
# an unrecognised reply is treated as a correction and throws the draft
# away -- so a resident who described a problem in Nepali and confirmed it
# with "हो" lost the complaint instead of filing it.
AFFIRMATIVE = {
    'yes', 'y', 'yeah', 'yep', 'ok', 'okay', 'confirm', 'confirmed',
    'file it', 'submit', 'submit it', 'yes please', 'go ahead', 'send it',
    'yes file it', 'do it',
    'ho', 'huncha', 'thik cha', 'thik', 'pathau',      # romanised Nepali
    'हो', 'हुन्छ', 'ठीक', 'ठीक छ', 'ठिक छ', 'पठाऊ', 'पठाउनुहोस्',
    'हवस्', 'हस्', 'दर्ता गर्नुहोस्',                   # Devanagari
}
NEGATIVE = {
    'no', 'n', 'nope', 'cancel', 'stop', 'never mind', 'nevermind', 'chaina',
    'होइन', 'छैन', 'पर्दैन', 'रद्द', 'रद्द गर्नुहोस्',
}

# English, romanised Nepali and Devanagari. The Devanagari forms were missing,
# so a resident writing in the script the municipality itself publishes in
# could not report a problem by describing it.
CIVIC_KEYWORDS = {
    'ROAD': ('pothole', 'broken road', 'road damage', 'bad road', 'road repair',
             'sadak', 'सडक', 'खाल्डो', 'बाटो'),
    'SANITATION': ('garbage', 'trash', 'waste', 'litter', 'dirty street',
                   'rubbish', 'fohor', 'फोहोर', 'कसिंगर', 'फोहर'),
    'WATER': ('water leak', 'no water', 'water cut', 'dirty water', 'water pipe',
              'water supply', 'pani', 'पानी', 'धारा', 'खानेपानी'),
    'ELECTRICITY': ('power cut', 'no electricity', 'blackout', 'power failure',
                    'streetlight', 'street light', 'batti', 'बत्ती',
                    'बिजुली', 'लाइट', 'सडक बत्ती', 'सडक बत्ति'),
    'NOISE': ('loud noise', 'noise pollution', 'noisy', 'हल्ला', 'ध्वनि'),
    'INFRASTRUCTURE': ('broken bridge', 'drainage', 'sewer', 'blocked drain',
                       'footpath', 'pavement', 'ढल', 'पुल', 'नाली'),
}

REPORT_INTENT = ('report a', 'report the', 'complain', 'file a', 'there is a',
                 'there is', 'broken', 'gunaso', 'ujuri')

# These tools take no arguments: they return the whole list and cannot narrow
# it. That makes them the right answer to "what is there to see" and the
# wrong answer to a question about one thing. "What should I wear to the
# temples?" matched the bare word "temple" and came back as a list of places
# to visit, while the page that answers it -- Visitor Guidelines, which says
# dress modestly and remove your shoes -- was never consulted.
BROWSE_ROUTES = {'find_attractions', 'find_businesses'}



# "when is garbage collected" names a category but asks a question about the
# service. Starting a complaint there answers a question with a form.
ASKING_EN = re.compile(
    r'^\s*(?:when|what|which|where|how|who|why|is|are|does|do|can|could)\b')

# Matched as plain substrings: Python's \b is defined by \w boundaries and
# does not reliably separate Devanagari words, so anchoring on it silently
# failed and "फोहोर कहिले उठाउँछ" opened a complaint instead of
# answering the question.
ASKING_NE = ('कहिले', 'कसरी', 'कहाँ', 'कति', 'के हो', 'को हो')


def _is_a_question(lowered):
    return bool(ASKING_EN.search(lowered)) or any(w in lowered for w in ASKING_NE)


def _has_report_intent(lowered):
    """Word-boundary match.

    Both ends matter. A leading boundary alone still let "complain" fire on
    "list every complaint with phone numbers" — a request for data, not a
    report — because "complaints" starts with "complain".
    """
    return any(re.search(rf'\b{re.escape(phrase)}\b', lowered)
               for phrase in REPORT_INTENT)


# A resident who writes in Devanagari was answered in English for the whole
# filing conversation: "सडक बत्ती बिग्रियो" got back "I can file a Road
# complaint about that." The municipality publishes in Nepali, so this is
# the language the form should speak too.
CATEGORY_NE = {
    'ROAD': 'सडक',
    'SANITATION': 'सरसफाइ',
    'WATER': 'खानेपानी',
    'ELECTRICITY': 'बिजुली',
    'NOISE': 'ध्वनि प्रदूषण',
    'INFRASTRUCTURE': 'पूर्वाधार',
}
CATEGORY_LIST_NE = 'सडक, सरसफाइ, खानेपानी, बिजुली, ध्वनि प्रदूषण वा पूर्वाधार'


def _in_nepali(message):
    """True when the citizen wrote in Devanagari."""
    from chatbot.tools.retrieval import _is_devanagari
    return _is_devanagari(message)


def _say(nepali, english, ne):
    """Pick the reply language chosen at the start of the conversation."""
    return nepali if ne else english


def _normalise(message):
    return (message or '').strip().lower().rstrip('.!?')


def detect_category(lowered):
    """Pick the category whose longest keyword the message matches.

    First-match-by-dict-order sent "सडक बत्ती बिग्रियो" -- a broken street
    light -- to ROAD, because "सडक" (road) is a ROAD keyword and appears
    before ELECTRICITY in the table. The English "my street light is broken"
    was right only by luck: "street light" is one ELECTRICITY phrase and
    "street" alone is not a ROAD keyword, so nothing competed.

    A longer keyword is a more specific claim about the message, so it wins.
    That holds in either language without needing a rule per compound.
    """
    best_category, best_length = None, 0
    for category, words in CIVIC_KEYWORDS.items():
        for word in words:
            if word in lowered and len(word) > best_length:
                best_category, best_length = category, len(word)
    return best_category


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
    # A category word alone is not a report. An explicit reporting verb still
    # wins, so "when did you fix it" stays a question but "report a broken
    # streetlight" is still a report.
    reporting = _has_report_intent(lowered) or (
        bool(detect_category(lowered)) and not _is_a_question(lowered)
    )

    if not in_progress:
        routed = route(message, claim_token=claim_token)
        if routed:
            name, kwargs = routed
            # A get_* match is an explicit personal lookup ("my complaints")
            # and wins outright. The rest are broad topic matches, which yield
            # to a report so a complaint is never answered with sightseeing.
            if name.startswith('get_') or not reporting:
                # A question deserves an answer before a catalogue. The
                # listing still stands in when nothing answers it.
                if name in BROWSE_ROUTES and _is_a_question(lowered):
                    answered = _knowledge_fallback(request, message)
                    if answered is not None:
                        return answered
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

    # Fixed when the conversation opens: a follow-up naming a landmark may
    # be in Latin script even from someone who began in Nepali, so the reply
    # language must not be re-decided on every message.
    ne = slots.get('ne') if started else _in_nepali(message)

    if not started:
        category = detect_category(lowered)
        wants_to_report = _has_report_intent(lowered)
        # Same rule as the caller: a category word inside a question is a
        # question. "When is garbage collected" must not open a complaint.
        if category and not wants_to_report and _is_a_question(lowered):
            return None
        if not category and not wants_to_report:
            return None
        if not category:
            return (_say(
                f'यो म दर्ता गर्न सक्छु। कस्तो समस्या हो — {CATEGORY_LIST_NE}?',
                'I can file that for you. What kind of issue is it — '
                'roads, sanitation, water, electricity, noise or '
                'infrastructure?', ne), [], 'complaint_filing')
        slots = {'category': category, 'description': message.strip(),
                 'ne': ne}
        session[SLOTS_KEY] = slots
        label = CATEGORY_NE.get(category, category.title())
        return (_say(
            f'**{label}** सम्बन्धी उजुरी दर्ता गर्न सक्छु। '
            'यो कहाँ हो? नजिकको चिनारी वा बाटोको नाम भए पुग्छ।',
            f"I can file a **{category.title()}** complaint about that. "
            'Where is it? A landmark or street name is enough.', ne),
            [], 'complaint_filing')

    if not slots.get('category'):
        category = detect_category(lowered)
        if not category:
            return (_say(
                f'कृपया समस्याको प्रकार बताउनुहोस् — {CATEGORY_LIST_NE}?',
                'I still need the category — roads, sanitation, water, '
                'electricity, noise or infrastructure?', ne),
                [], 'complaint_filing')
        slots['category'] = category
        session[SLOTS_KEY] = slots
        return (_say('बुझेँ। समस्या कहाँ छ?',
                     'Got it. Where is the problem?', ne),
                [], 'complaint_filing')

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
            return (_say('कुन नाममा दर्ता गरूँ?',
                         'And what name should I file it under?', ne),
                    [], 'complaint_filing')

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
