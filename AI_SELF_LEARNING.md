# Municipal AI — Self-Learning Architecture

## What Was Built

Four self-learning layers were added to the chatbot AI engine to make it smarter over time without manual updates.

---

## Level 1 — Semantic Search (Vector Embeddings)

**File:** `chatbot/ai_engine.py` — `_embed()`, `_cosine_sim()`, `_semantic_search_kb()`

**How it works:**
- Every user query is converted into a 768-dimensional embedding vector using Groq's `nomic-embed-text-v1.5` model
- The query vector is compared against all stored KB entry vectors using cosine similarity
- Top 5 most semantically similar KB entries are injected into the AI context

**Why it matters:**
- Before: "places of worship" → no results (keyword "temple" not in query)
- After: "places of worship" → finds Nyatapola Temple, Changu Narayan (meaning matched, not words)

**Embedding generation:**
- New KB entries get embedded on creation
- Existing entries without embeddings are embedded 3-at-a-time per request (fills itself in gradually)
- Embeddings stored as JSON arrays in the `knowledge_base.embedding` column

---

## Level 2 — Self-Growing Knowledge Base

**File:** `chatbot/ai_engine.py` — `_maybe_auto_save_kb()`, `_log_unanswered()`

### Auto-save good answers
When Groq gives a useful response (>150 chars, no error phrases), it is automatically saved as a new KB entry:
- Title = the original user question
- Content = the Groq response
- Category = derived from detected intent
- `auto_generated = True`, `priority = -1` (lower than human-authored entries)
- Embedding generated and stored immediately

**Effect:** The second user who asks the same question gets served from KB instantly. No Groq API call needed.

### Unknown question tracker
When the AI falls back (no API key configured) or a user clicks 👎, the question is logged to `UnansweredQuery`:

| Field | Purpose |
|---|---|
| `query` | Original user question |
| `normalized` | Lowercased/stripped for deduplication |
| `ask_count` | How many times this was asked (auto-increments) |
| `is_resolved` | Admin marks resolved after adding a KB entry |
| `resolution_kb` | FK to the KB entry that answered it |

**Effect:** Admin sees "47 users asked about wheelchair access this week" → adds one KB entry → all future users get a perfect answer.

---

## Level 3 — User Memory & Personalisation

**File:** `chatbot/ai_engine.py` — `_get_user_context()`, `_update_user_profile()`  
**Model:** `chatbot/models.py` — `UserAIProfile`

### What is remembered (per user, across sessions)

| Signal | Detected from query | Stored as |
|---|---|---|
| Dietary preference | "vegetarian", "vegan", "halal" | `preferences.dietary` |
| Budget | "cheap", "budget", "luxury", "premium" | `preferences.budget` |
| Group type | "family", "kids", "solo", "couple", "honeymoon" | `preferences.group` |
| Visited places | "already visited X", "been to X" | `visited_attractions[]` |

### How it affects responses
The user profile is injected into the system prompt as:
```
USER PROFILE (personalise your answer):
Dietary: vegetarian
Budget: budget-conscious
Travelling as: family with children
Already visited: Durbar Square, Nyatapola Temple
```

The AI automatically avoids recommending already-visited places and suggests vegetarian restaurants without being asked.

---

## Level 4 — Feedback Loop

**File:** `chatbot/views.py` — `message_feedback()`  
**Model:** `chatbot/models.py` — `ResponseFeedback`  
**Template:** `templates/chatbot/chat.html` — 👍/👎 buttons

### How it works
- Every AI response shows 👍 and 👎 buttons in the chat UI
- Button click POSTs to `/chat/feedback/` with `message_id` and `rating` (1 or -1)
- One vote per message per user/session (duplicates update the existing vote)
- 👎 automatically logs the triggering question to `UnansweredQuery` for admin review

### The learning loop
```
User asks question
    ↓
AI answers
    ↓
User clicks 👍 or 👎
    ↓
👍 → nothing (good answer, keep in KB)
👎 → question logged to UnansweredQuery
    ↓
Admin reviews top unanswered queries weekly
    ↓
Admin adds KB entry
    ↓
All future users get better answer
```

---

## New Database Tables

```
unanswered_queries      — questions the AI couldn't answer well
response_feedback       — thumbs up/down on each AI response
user_ai_profiles        — per-user preferences learned from conversation
```

### New columns on `knowledge_base`

| Column | Type | Purpose |
|---|---|---|
| `embedding` | JSON | Stored vector (768 floats) for semantic search |
| `auto_generated` | Boolean | True = written by AI from conversation |
| `source_query` | Text | Original user question that generated this entry |

---

## Migration

When MySQL is running, apply the migration:

```bash
python manage.py migrate
```

This runs `chatbot/migrations/0003_self_learning.py` which:
- Removes `embedding_placeholder` (was a stub)
- Adds `embedding`, `auto_generated`, `source_query` to `knowledge_base`
- Creates `unanswered_queries`, `response_feedback`, `user_ai_profiles` tables

---

## Summary: Before vs After

| Capability | Before | After |
|---|---|---|
| Retrieval method | Keyword matching | Semantic vector similarity + keywords |
| KB growth | Manual only | Auto-grows from every good Groq response |
| Unknown questions | Silent failure | Logged, counted, surfaced for admin |
| User memory | None (stateless) | Preferences + visited places remembered |
| Feedback | None | 👍/👎 on every response, bad answers flagged |
| KB entry count over time | Static (18 entries) | Grows with every conversation |
