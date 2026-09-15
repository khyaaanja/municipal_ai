# TODO: Fix Groq 413 Token Limit Error

## Problem
`llama-3.1-8b-instant` free tier has 6000 TPM limit. Requests with full context (~12000 chars + history + max_tokens=1024) exceed this, causing 413 error.

## Steps

### Step 1: settings.py
- [x] Add `AI_FAST_MAX_TOKENS` setting (default: 512)

### Step 2: chatbot/ai_engine.py
- [x] Add `fast_max_tokens` attribute in `__init__`
- [x] Add `_build_compact_context()` method for fast model (reduces context ~90%)
- [x] Add `compact` parameter to `build_context_prompt()`
- [x] Add `compact` parameter to `_get_cached_city_data()`
- [x] Modify `chat()` to use compact context when fast model is selected
- [x] Modify `build_stream()` to use compact context when fast model is selected, with smaller max_tokens
- [x] Modify `_call_groq()` to use `fast_max_tokens` when using fast model
- [x] Fix fallback timeout path to also use `fast_max_tokens`

