# Implementation Plan — Fix AI Lag + "Limit After 2-3 Queries"

## Overview
Make the Municipal AI chatbot respond faster and stop hitting the Groq API limit after 2–3 user queries.

The chatbot currently suffers from two user-facing problems:
1. **Lag** — responses feel slow because the main 70B Groq call uses a 5-second timeout, constantly times out, and then **falls back** to a second (fast-model) Groq call. That doubles the latency and cost of almost every query. A hidden extra Groq call (`_extract_preferences_with_llm`) also fires on every authenticated query, consuming tokens and adding work.
2. **"Limit after 2–3 queries"** — the app is almost certainly on the **Groq free tier**, which caps `llama-3.3-70b-versatile` at **6,000 tokens/minute (TPM)**. Each full 70B query sends ~12,000 chars of context (~3,000 tokens) plus up to 1,024 output tokens ≈ **4,000+ tokens per query**. Two queries therefore exhaust the 6,000 TPM budget, so the **third query is rejected with a 429 rate-limit error** — exactly the "works 2–3 times then stops" behaviour reported. The extra preference-extraction Groq call on every authenticated query makes this worse.

This plan reduces the token footprint per query so more queries fit inside the TPM window, removes the double-call lag, and makes rate-limit handling graceful instead of hard-blocking. No working feature is removed — only the token budget, timeouts, and rate-limit bookkeeping are adjusted.

## Types
No new types, models, database fields, or migrations are required. All changes are configuration values, cache/TTL tuning, and routing/exception-handling logic.

## Files
Edits are confined to three existing Python files; one new plan file exists (this document). No templates, models, or migrations change.

- `municipal_ai/settings.py` (modified) — lower default token/context budgets for the Groq free tier.
- `chatbot/ai_engine.py` (modified) — fix the 70B timeout, disable silent client retries, catch Groq rate-limit errors gracefully, route more queries to the fast model, skip the expensive LLM preference extraction unless the query actually mentions preferences.
- `chatbot/views.py` (modified) — consolidate rate limiting so the global middleware and the endpoint-specific limits don't double-count; raise the chat endpoint limits.

## Functions

### Modified: `municipal_ai/settings.py`
1. **`AI_MAX_TOKENS`** default `1024 → 512` (keep env-overridable). Halves the output-token cost of the 70B model. The continuation logic still appends if the model hits `finish_reason == 'length'`, so long answers are preserved.
2. **`AI_MAX_CONTEXT_CHARS`** default `12000 → 8000` (keep env-overridable). Reduces the input-token cost sent on every query while retaining the most relevant city data.

### Modified: `chatbot/ai_engine.py`
3. **`_call_groq()`** — 
   - Replace the per-model `timeout=5` for the main (70B) model with a sane timeout (`max(15, settings.GROQ_TIMEOUT)`). The 5s timeout was causing constant timeouts → fallback → doubled latency.
   - Create the Groq client with `max_retries=0` so the SDK doesn't silently retry on rate limits (retries just add lag and pile more rejected requests onto the TPM window).
   - Add a `try/except` for `groq.RateLimitError` (HTTP 429) that returns a friendly "I'm a little busy — please wait a moment and try again" message instead of triggering the generic fallback path.
4. **`_is_simple_query()`** — broaden the fast-model routing so more common queries (yes/no, hours, prices, contacts, directions) go to `llama-3.1-8b-instant` (free-tier TPM ~30,000, ~8× cheaper than the 70B). This offloads the expensive 70B model and frees its TPM budget for genuinely complex queries.
5. **`chat()`** — gate `_update_user_profile()` so the expensive `_extract_preferences_with_llm()` Groq call only fires when the query actually contains preference keywords (budget / dietary / group / family / solo / couple / already visited). For ordinary queries it falls back to cheap keyword extraction and skips the extra Groq call — saving roughly one 8B call per authenticated query.

### Modified: `chatbot/views.py`
6. **`_check_rate_limit()`** — keep the helper but raise the per-endpoint window limits from `60` → `120` (per hour) for `chat_stream`, `chat_api`, `chat_async`, and `voice`, since the real bottleneck is Groq TPM, not HTTP request volume. Prevents legitimate users from being hard-blocked by HTTP counters while Groq still has budget.
7. **Global middleware double-count fix** — in `core/middleware.py`, `RateLimitMiddleware` currently counts **every** `/api/` request, and the chat endpoints count themselves again. The homepage first calls `/api/chat/stream/` and, on failure, falls back to `/api/chat/` — so one user query can increment the global counter 2×. To stop this, exempt the chat/voice/scan endpoints from the global middleware (they already have endpoint-specific limits), so each query is counted exactly once.

## Classes
No class changes. `MunicipalAIEngine` and `CityContextRetriever` keep their existing structure and singleton pattern.

## Dependencies
No new packages. Uses the existing `groq` SDK, `django.core.cache`, and `threading`. The `groq.RateLimitError` exception is already part of the installed `groq` package.

## Testing
- Unit-test that `_call_groq` returns a graceful message on a simulated `RateLimitError` (429) rather than raising.
- Unit-test that `_is_simple_query` classifies typical yes/no, price, hours, and contact queries as `True` (fast model) and complex tourism/itinerary queries as `False`.
- Unit-test that `_update_user_profile` skips the LLM extraction Groq call when the message has no preference keywords (assert no extra call is made).
- Verify with `manage.py test chatbot` that existing chat tests still pass.
- Manual smoke test: send 5+ consecutive varied queries and confirm none are hard-blocked and responses feel snappier.

## Implementation Order
1. Lower `AI_MAX_TOKENS` and `AI_MAX_CONTEXT_CHARS` defaults in `municipal_ai/settings.py`.
2. Fix `_call_groq()` — sane timeout, `max_retries=0`, graceful `RateLimitError` handling.
3. Broaden `_is_simple_query()` to route more queries to the fast model.
4. Gate `_update_user_profile()` / `_extract_preferences_with_llm()` behind preference keywords.
5. Raise endpoint rate limits in `chatbot/views.py` and exempt chat/voice/scan from the global `RateLimitMiddleware` in `core/middleware.py`.
6. Run the chatbot test suite and a manual multi-query smoke test.
