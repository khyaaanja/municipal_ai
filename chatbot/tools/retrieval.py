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
    'कार्यालय': ('office', 'municipality'),
    'शुल्क': ('fee', 'charge', 'cost'),
    'कागजात': ('document', 'documents'),
    'आवेदन': ('application', 'apply'),
    'उजुरी': ('complaint',),
    'गुनासो': ('complaint', 'grievance'),
    'आपतकालीन': ('emergency',),
    'प्रहरी': ('police',),
    'यातायात': ('transport', 'bus'),
}

STOPWORDS = {
    'the', 'a', 'an', 'is', 'are', 'was', 'of', 'to', 'in', 'on', 'for',
    'and', 'or', 'i', 'my', 'me', 'do', 'how', 'what', 'where', 'when',
    'can', 'you', 'please', 'it', 'this', 'that', 'with', 'at', 'be',
    'हो', 'छ', 'को', 'मा', 'र', 'के', 'कसरी', 'लाई', 'बाट',
}


def tokenize(text):
    return [t.lower() for t in TOKEN.findall(text or '')]


def expand(tokens):
    """Add cross-language equivalents so either language can reach the other."""
    out = list(tokens)
    for token in tokens:
        out.extend(BILINGUAL.get(token, ()))
    return out


def _useful(tokens):
    return [t for t in tokens if t not in STOPWORDS and len(t) > 1]


def search(query, limit=5, chunks=None):
    """Return up to `limit` chunks ranked by BM25 against the query."""
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
    return [chunk for _, chunk in scored[:limit]]
