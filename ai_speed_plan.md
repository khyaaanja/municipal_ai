# AI Response Speed — Analysis & Implementation Plan

## Why the AI Feels Slow

The AI response pipeline has **7 sequential steps** before the user sees the first word. Each step adds latency:

```
Request → Rate Limit → Parse → Fast-path Check → Response Cache Check → 
Conversation Fetch → Intent Detection → Context Retrieval (DB!) → 
System Prompt Build → History Prep → Groq API Call → Save → Respond
```

**Measured latency breakdown (typical):**

| Step | Time | Notes |
|------|------|-------|
| Rate limit check | ~2ms | cache.incr — fast |
| Complaint/civic fast-path | ~5-15ms | DB queries for regex match |
| Response cache check | ~3ms | SHA256 + cache.get |
| Conversation get/create | ~10-30ms | DB query on `conversations` table |
| Message INSERT | ~5-10ms | DB write |
| **Context retrieval (cache miss)** | **200–800ms** | **8+ DB queries across apps** |
| **Embedding/vector search** | **300–1500ms** | **`nomic-embed-text-v1.5` API call** |
| System prompt building | ~3ms | String concat |
| **Groq LLM API call** | **800–3000ms** | **`llama-3.3-70b-versatile`** |
| AI message INSERT | ~5-10ms | DB write |
| Post-processing thread | ~5-20ms | Fire-and-forget (2 threads) |

**Total: ~1.5s–5.5s** before the user sees anything.

### The Top 5 Bottlenecks

**#1 🔴 `_get_cached_city_data()` cache TTL is only 120 seconds.**
Every 2 minutes, the next chat request pays 200–800ms building context from 8+ DB queries. For a site with sporadic traffic, this happens on nearly every query.

**#2 🔴 `_call_groq` uses the 70B model for EVERYTHING.**
Even simple questions like "Do they accept credit cards?" or "What time does it open?" are sent to `llama-3.3-70b-versatile` (3s response instead of 0.5s with the fast model). The fast model `llama-3.1-8b-instant` (8B params) is defined but **never used for chat**.

**#3 🟡 Non-streaming endpoint blocks.**
The `/api/chat/` endpoint waits for the ENTIRE Groq response (up to 3s) before returning anything to the frontend. The streaming endpoint exists but the homepage JS uses `POST /api/chat/` first, falling back to streaming only if that fails.

**#4 🟡 Embedding is called on every chat.**
`_embed()` in `chat()` calls the Groq embeddings API (`nomic-embed-text-v1.5`) every time. Combined with `_semantic_search_kb()`, this adds 300–1500ms to every query regardless of whether semantic search is needed.

**#5 🟡 Thread spawning overhead.**
Every `chat()` call spawns **2 daemon threads** — one for `_maybe_auto_save_kb()` and one for `_update_user_profile()`. Python threads have non-trivial overhead (memory + GIL contention).

---

## [Types]

**No new types needed.** All changes are configuration TTLs, routing logic, and cache keys.

## [Files]

**Modified files:**
1. `chatbot/ai_engine.py` — Model routing, embedding guard, context TTL
2. `chatbot/views.py` — Async by default, cache tuning
3. `core/views.py` — `scan_api` uses fast model for rate-limited vision calls

## [Functions]

### Modified: `chatbot/ai_engine.py`

1. **`_get_cached_city_data()`** — Increase cache TTL from 120s → 600s (10 minutes). Add a secondary per-source TTL so attractions (change rarely) are cached 30 min while events (change daily) are cached 10 min.

2. **`chat()`** — Add model routing:
   ```python
   # Use fast model for simple questions
   if self._is_simple_query(user_message):
       model = self.fast_model  # llama-3.1-8b-instant
   else:
       model = self.model       # llama-3.3-70b-versatile
   ```
   Where `_is_simple_query()` detects: yes/no questions, hours, prices, phone numbers, directions.

3. **`_embed()`** — Guard with a **semantic search threshold**: only call the embeddings API when the question is complex (>5 words AND contains domain-specific keywords like "temple", "jatra", "thangka", "entry fee"). Otherwise skip embedding entirely.

4. **`_call_groq()`** — Add a **response timeout model fallback**: if the 70B model takes > 5 seconds, cancel and retry with the 8B fast model.

5. **`build_stream()`** — Add the same model routing and embedding guard.

### Modified: `chatbot/views.py`

6. **`chat_api()`** — Remove thread spawning (already handled inside `engine.chat()`). Add response cache with **normalized key** (lowercase, trimmed).

7. **`chat_stream()`** — Default streaming path. Add a **head-start yield**: send a "typing" token immediately before calling the engine, so the frontend shows the loading indicator faster.

8. **`message_feedback()`** — Don't re-initialize the engine just to log an unanswered query. Use a standalone Celery task or direct DB update.

## [Dependencies]

**None.** No new packages. Uses existing `django.core.cache`, `Groq`, `threading`.

## [Testing]

- Verify response cache hits with normalized keys (case-insensitive).
- Verify fast model is used for simple queries (check logs for model name).
- Verify context TTL increase doesn't cause stale data (attractions/events changes at most daily).
- Verify embedding is skipped for short queries.

## [Implementation Order]

1. Increase `_get_cached_city_data()` TTL → 600s
2. Add `_is_simple_query()` + model routing in `chat()` and `build_stream()`
3. Add embedding guard — skip for queries < 5 words or no domain keywords
4. Add response cache key normalization (lowercase + strip)
5. Remove redundant threads (already handled in engine)
6. Optimize `message_feedback()` — no engine init
7. Add head-start yield in streaming endpoint
8. Add timeout fallback in `_call_groq()`

