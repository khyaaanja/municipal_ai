# AI Model Fallback System — Bhaktapur Municipal AI

## Problem

The chatbot's primary answer path depends on the Groq API (`llama-3.3-70b-versatile`). When Groq errors, times out, or rate-limits, the user currently gets a broken response or a generic failure. Since the platform already has a local knowledge base (ChromaDB → migrating to pgvector) with Bhaktapur-specific data, the system should fall back to answering **directly from that local data** instead of just failing.

## Goal

When the primary model call fails:
1. Retrieve relevant context from the local city database (RAG retriever) — this already happens for the primary path, so it's reused, not duplicated.
2. If local context is found, generate an answer without the LLM (extractive) or with a lightweight fallback model if one is configured.
3. If no local context matches, tell the user honestly rather than guessing.
4. Avoid hammering a dead API — use a circuit breaker so repeated requests during an outage skip straight to fallback.
5. Let the frontend know an answer was degraded, without making it feel broken.

---

## Prompt (for Claude Code / an agent to implement this)

Copy this into Claude Code, or use it as-is to brief whoever implements it:

```
I have a Django app (`municipal_ai`, chatbot module for Bhaktapur Municipality)
that answers user queries using the Groq API (llama-3.3-70b-versatile) with
RAG context pulled from a ChromaDB/pgvector retriever containing local city
data (complaints, tourism, business directory, FAQs).

I need a fallback system so that when the Groq call fails (timeout, rate
limit, API error, or any unexpected exception), the app still answers using
only the local retriever — no hard failures shown to the user.

Requirements:
1. Create an `AnswerEngine` class in `chatbot/services/answer_engine.py` that:
   - Always retrieves local context first (reuse the existing retriever
     interface — look at how the current chat view calls it).
   - Tries Groq first; on failure, falls back to an extractive answer built
     from the retrieved chunks (no LLM needed).
   - Supports an optional secondary/lightweight model for fallback phrasing,
     but must work correctly even without one.
   - Returns a dict with `answer`, `source` ("groq" | "fallback_model" |
     "local_db" | "none"), and `degraded` (bool).
2. Add a circuit breaker using Django's cache framework: after a Groq
   failure, skip calling Groq again for 60 seconds and go straight to
   fallback, to avoid retry storms during an outage.
3. Add a confidence threshold on retrieval similarity scores — only answer
   extractively when the top match is confident; otherwise return an honest
   "I don't have enough information" message with a pointer to contact the
   municipality office directly.
4. Wire this into the existing chatbot view/serializer so `source_note` is
   returned to the frontend when `degraded` is true (e.g. "Answered from
   local records"), without changing the response shape the frontend
   already expects for successful Groq answers.
5. Add logging (warning on Groq failure with exception type, error on
   unexpected exceptions) so I can monitor how often fallback triggers.
6. Write tests that simulate: Groq timeout, Groq rate limit, Groq generic
   exception, no local context found, and circuit breaker skipping a live
   call.

Look at the existing chatbot app structure first (models, views, the
current retriever class) before writing code, and match existing patterns
(naming, error handling style, app layout) rather than introducing a new
convention.
```

---

## Architecture

```
User query
   │
   ▼
Retriever.retrieve(query)  ──► local_chunks (from ChromaDB/pgvector)
   │
   ▼
Circuit breaker open? ──yes──► skip to Fallback
   │ no
   ▼
Call Groq (timeout ~8s)
   │
   ├─ success ──► return {answer, source: "groq", degraded: false}
   │
   └─ failure (APIError / Timeout / RateLimit / Exception)
         │
         ▼
      Set circuit breaker (60s)
         │
         ▼
      Fallback
         │
         ├─ local_chunks empty ──► honest "no info" message, source: "none"
         │
         ├─ fallback_model configured ──► try it, else fall through
         │
         └─ extractive answer from top chunks, source: "local_db"
```

## Core implementation

`chatbot/services/answer_engine.py`

```python
import logging
from django.core.cache import cache
from groq import APIError, APITimeoutError, RateLimitError

logger = logging.getLogger(__name__)

CIRCUIT_KEY = "groq_circuit_open"
CIRCUIT_TIMEOUT = 60  # seconds
CONFIDENCE_THRESHOLD = 0.55  # tune against your retriever's score scale


class AnswerEngine:
    def __init__(self, groq_client, retriever, fallback_model=None):
        self.groq_client = groq_client
        self.retriever = retriever
        self.fallback_model = fallback_model

    def answer(self, query: str) -> dict:
        local_chunks = self.retriever.retrieve(query, top_k=5)

        if cache.get(CIRCUIT_KEY):
            logger.info("Groq circuit open, skipping call")
            return self._fallback_answer(query, local_chunks)

        try:
            text = self._call_groq(query, local_chunks)
            return {"answer": text, "source": "groq", "degraded": False}

        except (APIError, APITimeoutError, RateLimitError) as e:
            logger.warning(f"Groq failed ({type(e).__name__}): {e}")
            cache.set(CIRCUIT_KEY, True, timeout=CIRCUIT_TIMEOUT)
            return self._fallback_answer(query, local_chunks)

        except Exception as e:
            logger.error(f"Unexpected error in AnswerEngine: {e}", exc_info=True)
            return self._fallback_answer(query, local_chunks)

    def _call_groq(self, query, local_chunks):
        context_text = "\n".join(c.text for c in local_chunks)
        prompt = self._build_prompt(query, context_text)
        resp = self.groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            timeout=8,
        )
        return resp.choices[0].message.content

    def _build_prompt(self, query, context_text):
        return (
            "You are Ask Bhaktapur AI, an assistant for Bhaktapur Municipality.\n"
            f"Local context:\n{context_text}\n\n"
            f"User question: {query}\n"
            "Answer clearly using the context above."
        )

    def _fallback_answer(self, query, local_chunks):
        if not local_chunks or local_chunks[0].score < CONFIDENCE_THRESHOLD:
            return {
                "answer": (
                    "I couldn't reach the AI service right now, and I don't have "
                    "confident matching information for this in our records. "
                    "Please try again shortly or contact the municipality office directly."
                ),
                "source": "none",
                "degraded": True,
            }

        if self.fallback_model:
            try:
                return {
                    "answer": self.fallback_model.generate(query, local_chunks),
                    "source": "fallback_model",
                    "degraded": True,
                }
            except Exception as e:
                logger.warning(f"Fallback model also failed: {e}")

        return {
            "answer": self._extractive_answer(local_chunks),
            "source": "local_db",
            "degraded": True,
        }

    def _extractive_answer(self, chunks):
        best = chunks[0]
        lines = [f"Based on our municipal records:\n\n{best.text}"]
        if len(chunks) > 1:
            lines.append("\nRelated information:")
            for c in chunks[1:3]:
                lines.append(f"- {c.text[:200]}...")
        return "\n".join(lines)
```

## Wiring into the view

```python
result = answer_engine.answer(query)
return JsonResponse({
    "message": result["answer"],
    "source_note": "Answered from local records" if result["degraded"] else None,
})
```

## Test cases to cover

| Scenario | Expected `source` | Expected `degraded` |
|---|---|---|
| Groq succeeds | `groq` | `False` |
| Groq times out, good local match | `local_db` | `True` |
| Groq rate-limited, fallback model set | `fallback_model` | `True` |
| Groq fails, no local match / low confidence | `none` | `True` |
| Circuit breaker open (recent failure) | `local_db` or `none` | `True` |

## Building out the local city database (so fallback can cover most queries)

The fallback is only as good as what's in the local database. Right now it likely covers whatever your existing 19 apps store (complaints, tourism, business directory, events, news). To make the extractive fallback genuinely useful when Groq is down, treat this as a content coverage problem, not just a technical one.

### 1. Data taxonomy — what to actually collect

| Category | Examples | Format |
|---|---|---|
| **Municipal services & procedures** | Birth/death certificate process, land registration, building permits, tax payment steps | FAQ pairs (question + answer) |
| **Office info** | Ward office locations, hours, contact numbers, department heads | Structured records |
| **Fees & documents required** | Document checklist per service, fee amounts | Structured tables |
| **Tourism & heritage** | Site descriptions, history, opening hours, entry fees, Taumadhi Square etc. | Long-form text chunks |
| **Business directory** | Name, category, location, hours, contact | Already structured (existing app) |
| **Events & news** | Upcoming events, recent announcements | Already structured (existing app) |
| **Complaints/status** | How to file, tracking process, common issue categories | FAQ + structured |
| **Emergency/essential contacts** | Police, hospital, municipality helpline | Structured records |
| **Common Q&A** | Whatever users actually ask most — pull this from chat logs once you have traffic | FAQ pairs |

### 2. Structure it for retrieval, not just storage

Two data shapes serve different purposes — don't lump everything into one long-text table:

- **FAQ/intent table** — for anything answerable in a fixed way (office hours, required documents, fees). Store as `question`, `answer`, `keywords/tags`, `category`. Check this table *first*, even before Groq, when there's a high-confidence match — it's faster and needs zero LLM.
- **Knowledge chunks for embedding** — for descriptive/long-form content (tourism, heritage, procedures with nuance). These get embedded into ChromaDB/pgvector as you're already doing.

```python
# models.py additions
class FAQEntry(models.Model):
    question = models.TextField()
    answer = models.TextField()
    category = models.CharField(max_length=50)  # e.g. "documents", "tax", "tourism"
    keywords = models.JSONField(default=list)    # for keyword pre-match before embedding search
    updated_at = models.DateTimeField(auto_now=True)

class KnowledgeChunk(models.Model):
    source_type = models.CharField(max_length=50)  # "tourism", "procedure", "service"
    title = models.CharField(max_length=200)
    content = models.TextField()
    embedding_id = models.CharField(max_length=100, null=True)  # id in ChromaDB/pgvector
```

### 3. Where the data comes from

- **Existing app data** — tourism, business directory, events, news apps already have structured data; write a management command to sync these into `KnowledgeChunk`/embeddings whenever they're created/updated (Django signal or a Celery periodic task), so the RAG index never goes stale.
- **Municipality staff** — office hours, procedures, fees change; these need a simple admin-editable `FAQEntry` table rather than being hardcoded, so non-developers can keep it current.
- **Real user questions** — once the chatbot has traffic, log queries that hit low-confidence fallback (`source: "none"`) and periodically review them to add missing FAQ entries. This is the single best way to close coverage gaps — the gaps are defined by real usage, not guesswork.

### 4. Ingestion command to keep embeddings in sync

```python
# management/commands/sync_knowledge_base.py
from django.core.management.base import BaseCommand
from chatbot.models import KnowledgeChunk
from chatbot.services.retriever import Retriever  # your existing ChromaDB/pgvector wrapper

class Command(BaseCommand):
    help = "Re-embed all KnowledgeChunk and FAQEntry content into the vector store"

    def handle(self, *args, **options):
        retriever = Retriever()
        chunks = KnowledgeChunk.objects.all()
        for chunk in chunks:
            embedding_id = retriever.upsert(
                text=chunk.content,
                metadata={"title": chunk.title, "source_type": chunk.source_type},
            )
            chunk.embedding_id = embedding_id
            chunk.save(update_fields=["embedding_id"])
        self.stdout.write(f"Synced {chunks.count()} knowledge chunks")
```

Run this on a schedule (Celery beat, since you already use Celery) or trigger it via a Django signal when `FAQEntry`/`KnowledgeChunk` records change.

### 5. Realistic expectation

No local database will cover *every* possible query — free-form questions, follow-ups, and anything requiring reasoning across multiple facts will still need Groq. The goal isn't 100% coverage; it's making sure the ~80% of queries that are repetitive, procedural, or informational (hours, fees, "how do I...", "what is...") still get answered correctly when the LLM is unavailable, and being honest ("I don't have enough information") for the rest instead of guessing.

## Notes specific to your setup

- Reuse whatever retriever interface `municipal_ai`'s chatbot app already has for ChromaDB — don't build a second one; once the pgvector migration lands, only the retriever's internals change, not this engine.
- The `CONFIDENCE_THRESHOLD` value depends on the similarity metric your retriever returns (cosine vs. distance) — check that before tuning it.
- Since Phase 1 hosting is zero-budget cPanel shared hosting, Django's default cache (locmem) works for the circuit breaker as long as you're on a single worker process; if you move to multiple workers/Gunicorn workers, switch to a shared cache backend (e.g. `django-redis`, which you're already using for Celery) so the circuit breaker state is shared.
