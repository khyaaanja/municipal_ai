"""Lexical retrieval over KnowledgeChunk.

Replaces substring matching, which could only ever return a chunk that
contained the query verbatim. A citizen asking "कर कसरी तिर्ने?" shares no
substring with a chunk titled "Property Tax Payment", so icontains returned
nothing however good the content was.

Scoring is BM25-style term overlap over a Devanagari-aware tokeniser, with a
small bilingual term map so a Nepali query can reach English content and the
reverse. No external service and no embedding model: it runs offline, in the
test suite, and on shared hosting.
"""
import math
import re
from collections import Counter

# Devanagari occupies U+0900–U+097F. \w under re.UNICODE already covers it,
# but splitting on it explicitly keeps the intent obvious.
TOKEN = re.compile(r'[0-9A-Za-zऀ-ॿ]+', re.UNICODE)

K1 = 1.5   # term-frequency saturation
B = 0.75   # length normalisation

# Terms a citizen is likely to use in one language against content written in
# the other. Deliberately small and hand-checked rather than machine-translated.
BILINGUAL = {
    'कर': ('tax', 'taxation', 'revenue'),
    'तिर्ने': ('pay', 'payment'),
    'तिर्नु': ('pay', 'payment'),
    'भुक्तानी': ('payment', 'pay'),
    'नागरिकता': ('citizenship', 'citizen'),
    'सिफारिस': ('recommendation', 'certificate'),
    'जन्म': ('birth',),
    'मृत्यु': ('death',),
    'विवाह': ('marriage', 'wedding'),
    'नक्सा': ('map', 'building', 'permit'),
    'पानी': ('water', 'supply'),
    'बत्ती': ('electricity', 'light', 'power'),
    'सडक': ('road', 'street'),
    'फोहोर': ('garbage', 'waste', 'sanitation'),
    'अस्पताल': ('hospital', 'health'),
    'विद्यालय': ('school', 'education'),
    'मन्दिर': ('temple', 'heritage'),
    'जात्रा': ('festival', 'jatra'),
    'वडा': ('ward',),
    # Social-protection services. The charter documents both -- section 27
    # distributes the identity card that entitles someone to the social
    # security allowance, section 28 covers the disability card -- and
    # neither was reachable from English, so two services the municipality
    # actually delivers were being reported as gaps.
    'भत्ता': ('allowance', 'benefit', 'pension'),
    'ज्येष्ठ': ('senior', 'elderly', 'old'),
    'सुरक्षा': ('security', 'protection'),
    'अपाङ्गता': ('disability', 'disabled', 'handicap'),
    'परिचयपत्र': ('card', 'identity'),
    # The scanned charter came through Preeti conversion with these
    # spellings, and a term nobody spells that way is a term nobody reaches.
    'ज्येषठ': ('senior', 'elderly', 'old'),
    'अपांगता': ('disability', 'disabled', 'handicap'),
    'अपांग': ('disability', 'disabled', 'handicap'),
    # Recovered by repairing the scanned text: these were spelled with a
    # digit standing in for a consonant and could not be reached in either
    # language until the conversion was fixed.
    'कम्पोषट': ('compost', 'composting'),
    'कम्पोस्ट': ('compost', 'composting'),
    'ढल': ('sewer', 'drain', 'drainage'),
    'जडान': ('connection',),
    'कार्यालय': ('office', 'municipality'),
    'शुल्क': ('fee', 'charge', 'cost'),
    'कागजात': ('document', 'documents'),
    'आवेदन': ('application', 'apply'),
    'उजुरी': ('complaint',),
    'गुनासो': ('complaint', 'grievance'),
    'आपतकालीन': ('emergency',),
    'प्रहरी': ('police',),
    'यातायात': ('transport', 'bus'),

    # The tax and fee categories the Act actually charges on. Without these an
    # English question names a category the documents only hold in Devanagari.
    # Deliberately not 'shop': it pulled a shopping guide above the Act
    # that sets the business tax rate.
    'व्यवसाय': ('business', 'trade', 'enterprise'),
    'बहाल': ('rent', 'rental', 'lease', 'tenancy'),
    'सम्पत्ति': ('property', 'asset'),
    'मालपोत': ('land', 'revenue'),
    'जग्गा': ('land', 'plot'),
    'घर': ('house', 'home', 'building'),
    'सवारी': ('vehicle', 'car'),
    'विज्ञापन': ('advertisement', 'advertising', 'signboard'),
    'दर': ('rate', 'rates'),
    'नवीकरण': ('renewal', 'renew'),
    'दर्ता': ('registration', 'register'),
    'प्रमाणपत्र': ('certificate',),
    'अनुमति': ('permission', 'permit'),
    'पर्यटन': ('tourism', 'tourist'),
    'सरसफाइ': ('sanitation', 'cleaning'),
}

STOPWORDS = {
    'the', 'a', 'an', 'is', 'are', 'was', 'of', 'to', 'in', 'on', 'for',
    'and', 'or', 'i', 'my', 'me', 'do', 'how', 'what', 'where', 'when',
    'can', 'you', 'please', 'it', 'this', 'that', 'with', 'at', 'be',
    'हो', 'छ', 'को', 'मा', 'र', 'के', 'कसरी', 'लाई', 'बाट',

    # Conversational filler. "Tell me about Nyatapola" is a question about
    # Nyatapola; counting "tell" and "about" as content made a perfect match
    # score one word in three.
    'tell', 'about', 'know', 'want', 'need', 'give', 'show', 'find', 'get',
    'looking', 'could', 'would', 'should', 'many', 'much', 'any', 'some',
    'there', 'here', 'does', 'did', 'has', 'have', 'from', 'more', 'like',
    'भन्नुहोस्', 'चाहन्छु', 'दिनुहोस्', 'बारे',
}


# BILINGUAL is written Nepali-first because the source documents are Nepali,
# but a question arrives in either language. The reverse index is derived from
# it rather than maintained by hand, so the two cannot drift apart.
# Ways visitors phrase the same need. The content existed for most of these
# already — "Accommodation in Bhaktapur" scored 1.00 for "accommodation" and
# 0.00 for "where to stay" — so this is reach, not new material.
#
# Kept deliberately tight. A loose synonym costs precision: mapping व्यवसाय to
# "shop" once pulled a shopping guide above the Act that sets the business
# tax rate.
SYNONYMS = {
    'accommodation': ('stay', 'overnight', 'hotel', 'lodge', 'guesthouse',
                      'sleep', 'staying'),
    'restaurant': ('eat', 'food', 'dining', 'meal', 'lunch', 'dinner',
                   'breakfast', 'cuisine'),
    'fee': ('cost', 'costs', 'price', 'charge'),
    'transport': ('bus', 'taxi', 'reach', 'travel', 'arrive', 'journey'),
    'festival': ('jatra', 'celebration', 'procession'),
    'pottery': ('ceramic', 'clay', 'potter'),
    'heritage': ('unesco', 'historic', 'historical', 'ancient'),
    'dress': ('wear', 'clothing', 'clothes', 'attire', 'modest'),
    # Nepali to Nepali. Until now the map only crossed languages, so a
    # citizen and the citizen charter could use two words for one thing and
    # never meet. The charter documents a water connection as "धारा/विद्ुत
    # जडान सिफारिस"; a resident asks "पानीको धारा कसरी जोड्ने". Only "धारा"
    # was shared, one word of three, which scored below the gate and the
    # procedure -- which is written down, with its documents and its fee --
    # was reported as something the municipality has no answer for.
    'धारा': ('पानी', 'खानेपानी'),
    'जडान': ('जोड्ने', 'जोड्न', 'जोडने'),
    # The lost-document entry says "theft"; a visitor says "stolen".
    'theft': ('stolen', 'stole', 'robbed', 'pickpocket', 'snatched'),
    # The rules say "Photography allowed"; a visitor asks about "photos".
    # Different stems, so the entry that answers scored only on the word
    # "temple" and lost to a list of temples.
    'photography': ('photo', 'picture', 'camera', 'photograph', 'filming'),
    'lost': ('missing', 'misplaced'),
}



ENGLISH_TO_NEPALI = {}
for _nepali, _english_terms in BILINGUAL.items():
    for _english in _english_terms:
        ENGLISH_TO_NEPALI.setdefault(_english, []).append(_nepali)


# Nepali attaches case endings to the noun, so "नगरपालिकाको" and
# "नगरपालिका" are the same word to a reader and different strings to a
# matcher. Trimming the common endings lets a question reach a document that
# uses the other form. Longest first, so "हरूको" is not left as "हरू".
NEPALI_SUFFIXES = (
    'हरूको', 'हरूलाई', 'हरूमा', 'हरूसँग', 'कोलागि',
    'सँग', 'देखि', 'बाट', 'लाई', 'हरू',
    'को', 'का', 'की', 'ले', 'मा',
)
# Two, not three: कर (tax) is a two-codepoint word, so a longer minimum
# silently refused to stem करको and left the question unable to reach the
# Act that sets the rate.
MIN_STEM = 2


# English needs the same treatment Nepali already had. "where can I eat"
# returned nothing at all -- not a weak match, nothing -- against a chunk
# reading "Best restaurants near Durbar Square. Avoid eating near temples",
# because "eat" is not "eating" and "restaurant" is not "restaurants". The
# same silent miss applied to fee/fees, temple/temples, hotel/hotels.
#
# This is a matcher, not a dictionary: both the question and the document go
# through it, so agreeing with itself matters more than being right about
# English. "buses" -> "buse" is wrong and still matches another "buses".
ENGLISH_SUFFIXES = ('ing', 'ed', 'es', 's')
# Enough must survive that the word is still itself: "bus" must not become
# "bu". Three is the shortest English noun that still reads as one.
MIN_STEM_EN = 3


def _stem_en(token):
    """Trim an English inflection when a real word is left behind."""
    for suffix in ENGLISH_SUFFIXES:
        if not token.endswith(suffix):
            continue
        if len(token) - len(suffix) < MIN_STEM_EN:
            continue
        # "address" and "process" are not plurals.
        if suffix == 's' and token.endswith('ss'):
            continue
        # Only a sibilant takes "es": taxes -> tax, but homes -> home, which
        # the plain "s" rule below handles. Without this, "taxes" stemmed to
        # "taxe" and could not reach a document saying "tax".
        if suffix == 'es' and not token[:-2].endswith(('s', 'x', 'z', 'ch', 'sh')):
            continue
        return token[: -len(suffix)]
    return token


def _stem(token):
    """Trim case endings or an inflection until the token stops changing.

    Stripping only once did not converge, and two spellings of one word
    landed in different places: "नगरपालिकाको" lost "को" and stopped at
    "नगरपालिका", while the bare "नगरपालिका" lost "का" and became
    "नगरपालि". A question about the municipality could not reach a document
    that named it. Repeating to a fixed point makes every form agree.
    """
    for _ in range(len(NEPALI_SUFFIXES)):
        for suffix in NEPALI_SUFFIXES:
            if token.endswith(suffix) and len(token) - len(suffix) >= MIN_STEM:
                token = token[: -len(suffix)]
                break
        else:
            break
    # Devanagari has no ASCII suffixes, so this only ever touches English.
    return _stem_en(token)


# The municipal documents were scanned out of the legacy Preeti font and the
# conversion drops conjuncts. The rules live with the converter; the matcher
# applies them too, so a document imported before the converter was fixed
# still meets a question that uses the correct spelling.
from chatbot.services.preeti import repair_text as repair_preeti


def tokenize(text):
    text = repair_preeti(text or '')
    return [_stem(t.lower()) for t in TOKEN.findall(text)]


# Built here rather than beside SYNONYMS because it has to agree with the
# stemmer. Documents are matched on stemmed tokens, so an entry keyed on the
# raw word is simply unreachable: "robbed" stems to "robb", and the synonym
# written as "robbed" was never once consulted. Both directions, and both
# sides of each pair, go through the same stemmer the text does.
# Deduplicated: "stay" and "staying" both stem to "stay", so an expansion
# listed twice would count twice in the BM25 sum and quietly overweight it.
SYNONYM_INDEX = {}
for _head, _forms in SYNONYMS.items():
    _stemmed_head = _stem(_head)
    for _form in _forms:
        _stemmed_form = _stem(_form)
        if _stemmed_form == _stemmed_head:
            continue
        SYNONYM_INDEX.setdefault(_stemmed_form, set()).add(_stemmed_head)
        SYNONYM_INDEX.setdefault(_stemmed_head, set()).add(_stemmed_form)
SYNONYM_INDEX = {_key: tuple(sorted(_values))
                 for _key, _values in SYNONYM_INDEX.items()}


def equivalents(token):
    """Other words for the same thing: across languages, and within English."""
    return (tuple(BILINGUAL.get(token, ()))
            + tuple(ENGLISH_TO_NEPALI.get(token, ()))
            + tuple(SYNONYM_INDEX.get(token, ())))


def expand(tokens):
    """Add cross-language equivalents so either language can reach the other.

    Without the English->Nepali direction the municipal documents, which are
    all Devanagari, were unreachable from an English question: "business tax"
    scored zero against the Act that sets the business tax rate.
    """
    out = list(tokens)
    for token in tokens:
        out.extend(equivalents(token))
    return out


DEVANAGARI = re.compile(r'[\u0900-\u097F]')
# A cited source is metadata, not language. Counting the letters in
# "https://ntb.gov.np/en/plan-your-trip/tourist-police" made a two-line
# Nepali entry read as English, which is the opposite of what citing a
# source should do to it.
URL = re.compile(r'https?://\S+|\b\S+\.(?:gov\.np|com|org|net)\S*')


def _is_devanagari(text):
    """True when the text is mostly Devanagari rather than Latin.

    Counted rather than sniffed, with URLs removed first: a Nepali entry
    citing an English source URL still reads as Nepali, and an English entry
    naming a Nepali place still reads as English.
    """
    body = URL.sub(' ', text or '')
    nepali = len(DEVANAGARI.findall(body))
    latin = sum(1 for ch in body if 'a' <= ch.lower() <= 'z')
    return nepali > latin


def _useful(tokens):
    return [t for t in tokens if t not in STOPWORDS and len(t) > 1]


# How many BM25 candidates to reconsider by coverage before cutting to
# `limit`. Wide enough that a better answer ranked fifth can still win,
# narrow enough that a weak match cannot climb on a single shared word.
RERANK_POOL = 8


def search(query, limit=5, chunks=None, with_scores=False):
    """Return up to `limit` chunks ranked by BM25 against the query.

    With `with_scores`, returns (chunk, score) pairs so the caller can turn
    the ranking into something a citizen can act on — a weak best match is
    worth flagging rather than presenting with the same certainty as a
    strong one.
    """
    from chatbot.models import KnowledgeChunk

    terms = _useful(expand(tokenize(query)))
    if not terms:
        return []


    if chunks is None:
        chunks = list(
            KnowledgeChunk.objects.filter(is_active=True)
            .values('id', 'title', 'content', 'source_type')
        )
    if not chunks:
        return []


    docs = []
    for chunk in chunks:
        tokens = _useful(tokenize(f"{chunk['title']} {chunk['content']}"))
        docs.append((chunk, Counter(tokens), len(tokens)))

    total = len(docs)
    avg_len = sum(length for _, _, length in docs) / total or 1

    doc_freq = Counter()
    for _, counts, _ in docs:
        for term in set(terms):
            if counts[term]:
                doc_freq[term] += 1

    scored = []
    for chunk, counts, length in docs:
        score = 0.0
        for term in terms:
            freq = counts[term]
            if not freq:
                continue
            idf = math.log(1 + (total - doc_freq[term] + 0.5) / (doc_freq[term] + 0.5))
            norm = freq * (K1 + 1) / (freq + K1 * (1 - B + B * length / avg_len))
            score += idf * norm
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda pair: pair[0], reverse=True)

    # BM25 alone ranks by term weight, which is not the same as answering the
    # question. "घर नक्सा पास कसरी गर्ने" put a hotel listing above the Act
    # that sets the building-permit fee, because the listing repeated a
    # common word often. Re-ranking the strongest candidates by how much of
    # the question each one actually addresses puts the Act back on top and
    # left every other probed query where it was.
    # Answer first, then the language the question was asked in, then BM25.
    # "tourist police" returned the Nepali entry to an English speaker,
    # because that entry cites its source -- ntb.gov.np/.../tourist-police --
    # and a URL tokenises into English words. Script is only a tiebreaker: a
    # citizen asking in Nepali about something documented only in English
    # must still be able to reach it.
    asked_in_nepali = _is_devanagari(query)
    pool = scored[: max(limit, RERANK_POOL)]
    pool.sort(
        key=lambda pair: (
            coverage(query, pair[1]),
            _is_devanagari(pair[1]['content']) == asked_in_nepali,
            pair[0],
        ),
        reverse=True,
    )
    top = pool[:limit]
    if with_scores:
        return [(chunk, score) for score, chunk in top]
    return [chunk for _, chunk in top]

def coverage(query, chunk):
    """Fraction of the question's own words this chunk addresses.

    Counted over the words the citizen actually typed, not the expanded set.
    Expansion turns "कर" into four alternatives, and a chunk will rarely
    contain all of them — scoring against the expansion made a good match
    look like a poor one purely because the query had been broadened.
    Each original word counts as covered if any of its alternatives appear.
    """
    originals = _useful(tokenize(query))
    if not originals:
        return 0.0
    present = set(_useful(tokenize(f"{chunk['title']} {chunk['content']}")))
    matched = sum(
        1 for term in originals
        if term in present or any(alt in present for alt in equivalents(term))
    )
    return matched / len(originals)
