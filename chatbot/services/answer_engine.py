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

_QUERY_STOPWORDS = {
    'a', 'an', 'and', 'are', 'about', 'can', 'do', 'does', 'for', 'how',
    'i', 'in', 'is', 'it', 'me', 'my', 'near', 'of', 'on', 'the', 'there',
    'to', 'what', 'where', 'which', 'with', 'you',
}

logger = logging.getLogger(__name__)

CIRCUIT_KEY = "groq_circuit_open"
CIRCUIT_TIMEOUT = 60  # seconds
CONFIDENCE_THRESHOLD = 0.30  # cosine similarity — lower bound for extractive answers

NO_INFO_MESSAGE = (
    "माफ गर्नुहोस्, यस विषयमा अहिले जानकारी उपलब्ध छैन। "
    "कृपया फेरि प्रयास गर्नुहोस् वा भक्तपुर नगरपालिका कार्यालयमा सम्पर्क गर्नुहोस्: "
    "+977-1-6610000।\n\n"
    "Sorry, I don't have confident information on this right now. "
    "Please try again shortly or contact the Bhaktapur Municipality office directly: "
    "+977-1-6610000, or visit Dattatreya Square, Bhaktapur."
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
        """Return a list of LocalChunk objects with `.text` and `.score`."""
        city_data = self.retriever.retrieve(query, semantic_hits=self.semantic_hits)
        return self.chunks_from_city_data(
            city_data, semantic_hits=self.semantic_hits, query=query, top_k=top_k
        )

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
        lexical_overlap = LocalRetrieverAdapter._query_overlap(query, best.text)
        semantic_match = (
            getattr(best, 'source', '') == 'semantic_search'
            and best.score >= max(self.confidence_threshold, 0.55)
        )
        if (
            self.confidence_threshold >= CONFIDENCE_THRESHOLD
            and lexical_overlap < 0.08
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

    def _extractive_answer(self, chunks: list) -> str:
        """Build a readable answer from the top local chunks — no LLM needed."""
        best = chunks[0]
        lines = []
        if getattr(best, 'title', ''):
            lines.append(f"**{best.title}**")
        lines.append(f"Based on our municipal records:\n\n{best.text}")

        if len(chunks) > 1:
            lines.append("\nRelated information:")
            for c in chunks[1:3]:
                snippet = c.text[:200]
                if getattr(c, 'title', ''):
                    snippet = f"{c.title}: {snippet}"
                lines.append(f"- {snippet}...")

        lines.append(
            "\n\n_(Answered from local records — the live AI service is temporarily unavailable. "
            "For urgent help, call the municipality: +977-1-6610000.)_"
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
