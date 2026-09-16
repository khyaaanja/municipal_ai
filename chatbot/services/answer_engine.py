"""
AI Model Fallback System — AnswerEngine.

Primary answer path: Groq API (openai/gpt-oss-20b) with RAG context.
Fallback path:      local city database (ChromaDB / pgvector → MySQL KB),
                    extractive answers with NO LLM required.

Design goals:
1. Always retrieve local context first (reuse existing retriever interface).
2. Try Groq first; on any failure, fall back to extractive answers built from
   the retrieved chunks — never show a hard failure to the user.
3. Circuit breaker via Django's cache framework — after a Groq failure, skip
   calling Groq for 60 seconds to avoid retry storms during an outage.
4. Confidence threshold on retrieval similarity scores — only answer
   extractively when the top match is confident; otherwise return an honest
   "I don't have enough information" message.
5. `source` and `degraded` flags let the frontend know the answer came from
   the fallback without changing the response shape.
"""

import logging
import re
import time

from django.conf import settings
from django.core.cache import cache

from groq import APIError, APITimeoutError, RateLimitError
from .response_contract import answer_engine_response
from core import contacts

_QUERY_STOPWORDS = {
    'a', 'an', 'and', 'are', 'about', 'can', 'do', 'does', 'for', 'how',
    'i', 'in', 'is', 'it', 'me', 'my', 'near', 'of', 'on', 'the', 'there',
    'to', 'what', 'where', 'which', 'with', 'you',
}

logger = logging.getLogger(__name__)

CIRCUIT_KEY = "groq_circuit_open"
CIRCUIT_TIMEOUT = 60  # seconds
CONFIDENCE_THRESHOLD = 0.30  # cosine similarity — lower bound for extractive answers

# The reply a citizen gets when the assistant has nothing. It used to give
# out an unverified phone number and place the office at Dattatreya Square,
# neither of which the municipality publishes. Someone who has already failed
# to get an answer here is exactly the person who will act on whatever this
# says, so it now carries only what bhaktapurmun.gov.np states, and sends an
# emergency to the emergency services rather than to an office switchboard.
NO_INFO_MESSAGE = (
    "माफ गर्नुहोस्, यस विषयमा अहिले जानकारी उपलब्ध छैन। "
    "कृपया भक्तपुर नगरपालिका कार्यालयमा सम्पर्क गर्नुहोस्: "
    f"{contacts.PHONES_NE} ({contacts.EMAIL})।\n"
    f"{contacts.EMERGENCY_LINE_NE}\n\n"
    "Sorry, I don't have confident information on this right now. "
    "Please contact the Bhaktapur Municipality office directly: "
    f"{contacts.PHONES} ({contacts.EMAIL}), or see {contacts.WEBSITE}.\n"
    f"{contacts.EMERGENCY_LINE_EN}"
)


class LocalRetrieverAdapter:
    """
    Adapter that wraps the existing CityContextRetriever and exposes a
    `retrieve(query, top_k)` method returning a list of chunk objects with
    `.text` and `.score` attributes.

    This satisfies the AnswerEngine interface while reusing the existing
    retriever — no second retrieval pipeline is built. When the pgvector
    migration lands, only this adapter's internals change.
    """

    def __init__(self, retriever=None, semantic_hits=None):
        from chatbot.ai_engine import CityContextRetriever

        self.retriever = retriever or CityContextRetriever()
        self.semantic_hits = semantic_hits or []

    def retrieve(self, query: str, top_k: int = 5) -> list:
        """Return a list of LocalChunk objects with `.text` and `.score`.

        Indexed municipal documents come first. Without them the fallback saw
        only the keyword retriever's output, so "how many complaints are
        pending" came back as Bisket Jatra festival text under the heading
        "Based on our municipal records" — and questions the documents do
        answer, like the business tax rate, came back as no information.
        """
        chunks = self._municipal_chunks(query, top_k)
        chunks += self._learned_chunks(query, top_k)
        city_data = self.retriever.retrieve(query, semantic_hits=self.semantic_hits)
        chunks += self.chunks_from_city_data(
            city_data, semantic_hits=self.semantic_hits, query=query, top_k=top_k
        )
        return chunks[:top_k]

    @staticmethod
    def _learned_chunks(query: str, top_k: int) -> list:
        """Answers citizens previously marked helpful.

        Ranked below municipal documents on purpose: these are the
        assistant's own past output, kept because someone found them useful,
        not because the municipality published them. They carry their own
        source so nothing downstream can present them as record.
        """
        try:
            from chatbot.models import FAQEntry
            from chatbot.tools.retrieval import coverage
        except Exception:
            return []

        out = []
        try:
            for entry in FAQEntry.objects.filter(is_active=True).iterator():
                row = {'title': entry.question, 'content': entry.answer}
                score = coverage(query, row)
                if score < 0.5:          # a learned answer must closely match
                    continue
                # The marker is bookkeeping, not something a citizen reads.
                text = entry.answer.replace(LEARNED_MARKER, '', 1).strip()
                out.append(LocalChunk(
                    text=text, score=score, title=entry.question,
                    source='learned_answer', citation=entry.question[:80],
                ))
        except Exception:
            logger.exception('learned-answer lookup failed')
            return []
        out.sort(key=lambda c: c.score, reverse=True)
        return out[:top_k]

    @staticmethod
    def _municipal_chunks(query: str, top_k: int) -> list:
        """Top hits from the same index the assistant's tools search.

        Scored by how much of the question each passage covers, so a passage
        that shares nothing with the question scores zero and is dropped
        rather than presented as an answer.
        """
        try:
            from chatbot.tools.retrieval import coverage, search
        except Exception:
            return []

        # Matches the bar the assistant's own tools use. One word in three is
        # not an answer: at 0.33 "how many complaints are pending" returned
        # festival text under the heading "Based on our municipal records".
        MIN_COVERAGE = 0.35

        out = []
        try:
            for row in search(query, limit=top_k):
                score = coverage(query, row)
                if score < MIN_COVERAGE:
                    continue
                out.append(LocalChunk(
                    text=row['content'], score=score, title=row['title'],
                    source='municipal_document', citation=row['title'],
                ))
        except Exception:
            logger.exception('municipal retrieval failed in fallback')
            return []
        return out

    @classmethod
    def chunks_from_city_data(cls, city_data: dict, semantic_hits: list = None,
                              query: str = '', top_k: int = 5) -> list:
        """Build LocalChunk objects from an already-retrieved city_data dict.

        This lets the chat engine reuse its one retrieval pass instead of
        querying the DB twice when Groq fails.
        """
        semantic_hits = semantic_hits or []
        chunks = []

        # 1. Semantic hits (if provided externally) — highest fidelity
        for hit in semantic_hits:
            chunks.append(LocalChunk(
                text=hit.get('content') or hit.get('title', ''),
                score=float(hit.get('score', 0.0)),
                title=hit.get('title', ''),
                source=hit.get('source', 'semantic_search'),
                citation=hit.get('citation') or hit.get('title', 'semantic hit'),
            ))

        # 2. Keyword-search KB hits (kb:search) — direct relevance
        for entry in city_data.get('kb:search', []):
            chunks.append(LocalChunk(
                text=entry.get('content', ''),
                score=0.55,
                title=entry.get('title', ''),
                source=entry.get('source', 'knowledge_base'),
                citation=entry.get('citation') or f"knowledge_base:{entry.get('title', '')}",
            ))

        # 3. Category KB hits — broader but still relevant
        for key in ('kb:general', 'kb:heritage', 'kb:culture', 'kb:transport',
                    'kb:emergency', 'kb:services', 'kb:rules'):
            for entry in city_data.get(key, []):
                chunks.append(LocalChunk(
                    text=entry.get('content', ''),
                    score=0.45,
                    title=entry.get('title', ''),
                    source=entry.get('source', 'knowledge_base'),
                    citation=entry.get('citation') or f"knowledge_base:{entry.get('title', '')}",
                ))

        # FAQ and long-form chunks are optional models, so older deployments
        # without rows (or before their migration) remain fully compatible.
        for key in ('faq:search', 'kb:chunks'):
            for entry in city_data.get(key, []):
                chunks.append(LocalChunk(
                    text=entry.get('content', ''),
                    score=float(entry.get('score', 0.50)),
                    title=entry.get('title', ''),
                    source=entry.get('source', 'faq' if key.startswith('faq') else 'knowledge_chunk'),
                    citation=entry.get('citation') or f"{key}:{entry.get('title', '')}",
                ))

        # 4. Structured city data (attractions, events, etc.) — compact text
        for key in ('attractions', 'events', 'restaurants', 'hotels', 'products', 'news'):
            for item in city_data.get(key, []):
                chunks.append(LocalChunk(
                    text=cls._item_to_text(item),
                    score=0.40,
                    title=item.get('name') or item.get('title', ''),
                    source=f"city_database:{key}",
                    citation=item.get('citation') or f"city_database:{key}:{item.get('name') or item.get('title', '')}",
                ))

        # Keep the strongest representation of equivalent text, then rerank
        # with query terms so broad city data cannot displace direct matches.
        unique_by_text = {}
        for c in chunks:
            normalized = re.sub(r'\W+', ' ', c.text.lower()).strip()
            if not normalized:
                continue
            overlap = cls._query_overlap(query, c.text)
            c.score = min(1.0, c.score + (0.25 * overlap))
            previous = unique_by_text.get(normalized)
            if previous is None or c.score > previous.score:
                unique_by_text[normalized] = c

        unique = list(unique_by_text.values())
        unique.sort(key=lambda c: c.score, reverse=True)
        return unique[:top_k]

    @staticmethod
    def _query_overlap(query: str, text: str) -> float:
        query_terms = {
            t for t in re.findall(r"\w+", (query or "").lower())
            if len(t) > 2 and t not in _QUERY_STOPWORDS
        }
        text_terms = set(re.findall(r"\w+", (text or "").lower()))
        return len(query_terms & text_terms) / max(len(query_terms), 1)

    @staticmethod
    def _item_to_text(item: dict) -> str:
        """Flatten a structured item (attraction, event, etc.) into readable text."""
        parts = []
        for key, label in (
            ('name', ''), ('description', ''), ('address', 'Address'),
            ('entry_fee', 'Entry fee'), ('opening_hours', 'Hours'),
            ('date', 'Date'), ('venue', 'Venue'), ('rating', 'Rating'),
            ('phone', 'Phone'), ('category', 'Category'), ('price', 'Price'),
            ('title', ''), ('summary', ''), ('seller', 'Seller'),
        ):
            val = item.get(key)
            if val is None or val == '' or val == 0:
                continue
            if key == 'name' and 'title' in item and item['title']:
                continue  # skip redundant name when title exists
            if key == 'title' and 'name' in item and item['name']:
                continue
            if key == 'name':
                parts.append(str(val))
            elif label:
                parts.append(f"{label}: {val}")
            else:
                parts.append(str(val))
        return ' | '.join(parts)


# A passage must address at least this much of the question before it can be
# offered as the municipality's answer.
ANSWER_COVERAGE_MIN = 0.35

# Written by promote_helpful_answers; stripped before display.
LEARNED_MARKER = '[learned]'


def _strip_marker(text: str) -> str:
    """Remove internal bookkeeping before a citizen sees the text."""
    return (text or '').replace(LEARNED_MARKER, '', 1).strip()


def _covers_question(query: str, chunk) -> float:
    """Fraction of the question's words this chunk addresses, either language."""
    try:
        from chatbot.tools.retrieval import coverage
        return coverage(query, {'title': getattr(chunk, 'title', '') or '',
                                'content': getattr(chunk, 'text', '') or ''})
    except Exception:
        logger.exception('coverage check failed; treating as uncovered')
        return 0.0


class LocalChunk:
    """Minimal chunk object exposing `.text` and `.score` (duck-typed for tests)."""

    __slots__ = ('text', 'score', 'title', 'source', 'citation')

    def __init__(self, text: str, score: float, title: str = '',
                 source: str = 'knowledge_base', citation: str = ''):
        self.text = text
        self.score = score
        self.title = title
        self.source = source
        self.citation = citation or title


class AnswerEngine:
    """
    Orchestrates: retrieve → circuit check → Groq → fallback.

    Returns a dict:
        {
            'answer':  str,
            'source':  'groq' | 'fallback_model' | 'local_db' | 'none',
            'degraded': bool,
            'metadata': {
                'fallback': bool,
                'latency_ms': float,
                'request_id': str | None,
                ...
            },
        }
    """

    def __init__(self, groq_client=None, retriever=None, fallback_model=None,
                 api_key=None, model=None, timeout=None, circuit_timeout=None,
                 confidence_threshold=None):
        from groq import Groq

        self.api_key = api_key if api_key is not None else getattr(settings, 'GROQ_API_KEY', '')
        self.model = model or getattr(settings, 'GROQ_MODEL', 'openai/gpt-oss-20b')
        self.timeout = timeout if timeout is not None else max(
            15, getattr(settings, 'GROQ_TIMEOUT', 30)
        )

        self.groq_client = groq_client or (Groq(api_key=self.api_key, max_retries=0) if self.api_key else None)
        self.retriever = retriever or LocalRetrieverAdapter()
        self.fallback_model = fallback_model

        self.circuit_timeout = circuit_timeout if circuit_timeout is not None else CIRCUIT_TIMEOUT
        self.confidence_threshold = (
            confidence_threshold
            if confidence_threshold is not None
            else getattr(settings, 'ANSWER_CONFIDENCE_THRESHOLD', CONFIDENCE_THRESHOLD)
        )

    # ---- Public API ----------------------------------------------------------

    def answer(self, query: str) -> dict:
        """Main entry point. Returns {answer, source, degraded}."""
        started = time.perf_counter()

        def response(answer, source, degraded):
            return answer_engine_response(
                answer,
                source=source,
                degraded=degraded,
                sources=sorted({
                    getattr(c, 'source', 'knowledge_base') for c in local_chunks
                }),
                citations=[
                    {
                        'title': getattr(c, 'title', ''),
                        'citation': getattr(c, 'citation', None) or getattr(c, 'title', ''),
                        'score': round(c.score, 3),
                    }
                    for c in local_chunks[:5] if getattr(c, 'title', None) or getattr(c, 'citation', None)
                ],
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
            )

        try:
            local_chunks = self.retriever.retrieve(query, top_k=5)
        except Exception:
            logger.exception("AnswerEngine: local retrieval failed")
            local_chunks = []

        # Circuit breaker open → skip Groq entirely
        if self._circuit_is_open():
            logger.info("Groq circuit open, skipping call")
            return self._fallback_answer(query, local_chunks, response_factory=response)

        # No Groq client / no API key → no point trying
        if not self.groq_client or not self.api_key:
            logger.info("No Groq client configured, going straight to fallback")
            return self._fallback_answer(query, local_chunks, response_factory=response)

        try:
            text = self._call_groq(query, local_chunks)
            return response(text, 'groq', False)
        except (APIError, APITimeoutError, RateLimitError) as e:
            logger.warning("Groq failed (%s): %s", type(e).__name__, e)
            self._open_circuit()
            return self._fallback_answer(query, local_chunks, response_factory=response)
        except Exception as e:
            logger.error("Unexpected error in AnswerEngine: %s", e, exc_info=True)
            self._open_circuit()
            return self._fallback_answer(query, local_chunks, response_factory=response)

    # ---- Circuit breaker -----------------------------------------------------

    def _circuit_is_open(self) -> bool:
        """Check Django cache for the open-circuit flag."""
        try:
            return bool(cache.get(self._circuit_cache_key()))
        except Exception:
            # Cache unavailable → fail open (still try Groq)
            return False

    def _open_circuit(self):
        """Open the circuit breaker for `circuit_timeout` seconds."""
        try:
            cache.set(self._circuit_cache_key(), True, timeout=self.circuit_timeout)
        except Exception:
            logger.warning("Could not set circuit breaker cache key")

    def _circuit_cache_key(self) -> str:
        # Namespaced so tests can clear it without touching real cache
        return f"{CIRCUIT_KEY}:{self.model}"

    # ---- Groq call -----------------------------------------------------------

    def _call_groq(self, query: str, local_chunks: list) -> str:
        context_text = "\n".join(c.text for c in local_chunks)
        prompt = self._build_prompt(query, context_text)
        resp = self.groq_client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            timeout=self.timeout,
        )
        text = (resp.choices[0].message.content or '').strip()
        if not text:
            raise ValueError("Groq returned an empty response")
        return text

    def _build_prompt(self, query: str, context_text: str) -> str:
        return (
            "You are Ask Bhaktapur AI, an assistant for Bhaktapur Municipality.\n"
            f"Local context:\n{context_text}\n\n"
            f"User question: {query}\n"
            "Answer clearly using the context above."
        )

    # ---- Fallback ------------------------------------------------------------

    def _fallback_answer(self, query: str, local_chunks: list, response_factory=None) -> dict:
        response_factory = response_factory or (
            lambda answer, source, degraded: answer_engine_response(
                answer, source=source, degraded=degraded
            )
        )
        # Honest "no info" path — no confident match
        if not local_chunks or local_chunks[0].score < self.confidence_threshold:
            return response_factory(NO_INFO_MESSAGE, 'none', True)
        best = local_chunks[0]
        # How much of the question this passage actually addresses, counted
        # over the asker's own words and across languages. The previous gate
        # was an 8% lexical overlap, which almost nothing failed: "how many
        # complaints are pending" cleared it on festival text and was served
        # as "Based on our municipal records". Being one-directional, it also
        # rejected the tax Act for an English question about the tax Act.
        answered = _covers_question(query, best)
        semantic_match = (
            getattr(best, 'source', '') == 'semantic_search'
            and best.score >= max(self.confidence_threshold, 0.55)
        )
        if (
            self.confidence_threshold >= CONFIDENCE_THRESHOLD
            and answered < ANSWER_COVERAGE_MIN
            and not semantic_match
        ):
            return response_factory(NO_INFO_MESSAGE, 'none', True)

        # Optional lightweight fallback model for phrasing
        if self.fallback_model:
            try:
                return response_factory(
                    self.fallback_model.generate(query, local_chunks),
                    'fallback_model',
                    True,
                )
            except Exception as e:
                logger.warning("Fallback model also failed: %s", e)

        return response_factory(self._extractive_answer(local_chunks), 'local_db', True)

    @staticmethod
    def _dedupe(chunks: list) -> list:
        """One entry per passage.

        The same FAQ row can arrive from the learned lookup and from the
        keyword retriever, which put it in the answer and again under
        "Related information".
        """
        seen, out = set(), []
        for c in chunks:
            key = _strip_marker(getattr(c, 'text', ''))[:160]
            if key in seen:
                continue
            seen.add(key)
            out.append(c)
        return out

    def _extractive_answer(self, chunks: list) -> str:
        """Build a readable answer from the top local chunks — no LLM needed."""
        chunks = self._dedupe(chunks)
        best = chunks[0]
        lines = []
        if getattr(best, 'title', ''):
            lines.append(f"**{best.title}**")
        if getattr(best, 'source', '') == 'learned_answer':
            lines.append(
                "From an earlier answer that a resident marked helpful — not "
                "an official municipal record:\n\n" + _strip_marker(best.text))
        else:
            lines.append(
                f"Based on our municipal records:\n\n{_strip_marker(best.text)}")

        if len(chunks) > 1:
            lines.append("\nRelated information:")
            for c in chunks[1:3]:
                snippet = _strip_marker(c.text)[:200]
                if getattr(c, 'title', ''):
                    snippet = f"{c.title}: {snippet}"
                lines.append(f"- {snippet}...")

        lines.append(
            "\n\n_(Answered from local records — the live AI service is temporarily unavailable. "
            "For urgent help, call the municipality: " + contacts.PHONES + ".)_"
        )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Module-level convenience helpers for views/tasks
# ---------------------------------------------------------------------------

def get_answer_engine(**kwargs) -> AnswerEngine:
    """Return a cached AnswerEngine singleton with the standard retriever."""
    return AnswerEngine(**kwargs)


def _default_cache_key() -> str:
    """Cache key for the default model — shared between the engine and views."""
    model = getattr(settings, 'GROQ_MODEL', 'openai/gpt-oss-20b')
    return f"{CIRCUIT_KEY}:{model}"


def is_circuit_open() -> bool:
    """Module-level check: is the Groq circuit breaker currently open?"""
    try:
        return bool(cache.get(_default_cache_key()))
    except Exception:
        # Cache unavailable → fail open (still try Groq)
        return False


def open_circuit(timeout: int = None) -> None:
    """Module-level open: mark the Groq circuit breaker open for `timeout` seconds."""
    try:
        cache.set(_default_cache_key(), True, timeout=timeout or CIRCUIT_TIMEOUT)
    except Exception:
        pass


DEGRADED_RESPONSE_MARKERS = (
    "i'm having trouble connecting right now",
    "i'm having trouble responding right now",
    "i'm a little busy right now",
    "i've hit my response limit",
    "groq error:",
    "please try again in a moment",
)


def is_degraded_response(text: str) -> bool:
    """
    Heuristic: does this primary-engine response look like a degraded/fallback
    response (i.e. Groq failed and the old generic message was returned)?
    Used by views to decide whether to re-answer from local records.
    """
    t = (text or '').lower()
    return any(marker in t for marker in DEGRADED_RESPONSE_MARKERS)
