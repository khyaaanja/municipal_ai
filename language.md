# Implementation Plan: User Language Choice for AI Responses

## Overview

Enable users to choose their preferred language (English or Nepali) for AI assistant responses, with the language preference persisting across sessions for both authenticated and anonymous users, and the AI engine responding in the selected language naturally via the LLM system prompt.

## Scope & Context

The AI engine (`MunicipalAIEngine`) already has full multi-language support infrastructure:
- `SUPPORTED_LANGUAGES` dictionary mapping codes to display names (`en`, `ne`, `hi`, `zh-cn`, `bn`)
- `_detect_language()` auto-detects Nepali Devanagari script
- System prompt includes `{language}` placeholder instructing the LLM which language to respond in
- `chat()` and `build_stream()` already read `UserAIProfile.preferred_language` for authenticated users
- `set_language` view endpoint exists at `/chat/set-language/`

However, there are gaps:
1. **Anonymous users** — The `set_language` view requires `@login_required`, so anonymous users cannot save their preference. The frontend JS also wraps the toggle in `{% if user.is_authenticated %}`.
2. **Greeting response** — The hardcoded greeting in `MunicipalAIEngine.chat()` is always in English regardless of the selected language.
3. **Fallback responses** — `_fallback_response()` and `_service_unavailable_response()` are hardcoded English-only.
4. **Quick prompts** — The chat UI shows 10 quick prompt buttons in English only.
5. **Language persistence** — Anonymous users lose language preference on page refresh.

## Types

No new types or data structures are needed. The existing `SUPPORTED_LANGUAGES` dict and `UserAIProfile.preferred_language` char field are sufficient.

## Files

Files to be created:
- No new files needed.

Files to be modified:
1. `chatbot/views.py` — Remove `@login_required` decorator from `set_language()`, add session fallback for anonymous users
2. `chatbot/ai_engine.py` — Make greeting, fallback, and service_unavailable responses accept a `language` parameter
3. `templates/chatbot/chat.html` — Fix language toggle for anonymous users via localStorage, add Nepali quick prompts, fix initial language load

## Functions

### Modified Functions

#### 1. `chatbot/views.py:set_language()`
- **Current:** Decorated with `@login_required`, only saves to `UserAIProfile` (DB)
- **Changes:** 
  - Remove `@login_required` decorator
  - For authenticated users: save to `UserAIProfile` as before
  - For anonymous users: save language preference in `request.session['preferred_language']`
  - Return the saved language in response

#### 2. `chatbot/ai_engine.py:MunicipalAIEngine.chat()`
- **Current:** Greeting response is hardcoded English-only
- **Changes:** 
  - Detect language preference BEFORE the greeting fast-path
  - Move language detection logic above the `_is_greeting()` check
  - Pass `language` into greeting response context

#### 3. `chatbot/ai_engine.py:MunicipalAIEngine._fallback_response()`
- **Current:** Takes `(query, city_data)` — hardcoded English
- **Changes:**
  - Accept `language` parameter (default `'en'`)
  - No hard translation needed — the user said "let AI handle it"

#### 4. `chatbot/ai_engine.py:MunicipalAIEngine._service_unavailable_response()`
- **Current:** Hardcoded English
- **Changes:**
  - Accept `language` parameter (default `'en'`)
  - No hard translation needed — the user said "let AI handle it"

### New Functions
- No new functions needed.

## Classes

No class modifications needed. Methods within `MunicipalAIEngine` will be updated as described above.

## Dependencies

No new dependencies required.

## Testing

Manual testing:
1. **Authenticated user:** Click language toggle → refresh page → language should persist
2. **Anonymous user:** Click language toggle → refresh page → language should persist
3. **Nepali selected:** All quick prompts should show in Nepali
4. **English selected:** All quick prompts should show in English
5. **AI response:** With Nepali selected, AI responses should come in Nepali
6. **Greeting:** First message after language switch should respect selected language

## Implementation Order

1. Edit `chatbot/views.py` — Remove `@login_required`, add session fallback for anonymous users
2. Edit `chatbot/ai_engine.py` — Pass language into greeting, fallback, and service_unavailable responses
3. Edit `templates/chatbot/chat.html` — Fix frontend for anonymous language persistence, add Nepali quick prompts, fix initial language load
4. Write `language.md` (this document) as the implementation plan
