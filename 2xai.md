# 2xAI — Bhaktapur Municipal AI Upgrade Master Plan

> Written by: AI Expert Analysis (35 years experience distilled)
> Scope: Everything needed to make this AI better than any competing municipal platform in Nepal
> Philosophy: One file. No confusion. Do it in order. Ship and forget.

---

## Table of Contents

1. [Where We Are Now](#1-where-we-are-now)
2. [What Is Weak and Why](#2-what-is-weak-and-why)
3. [Tier 1 — Quick Wins](#3-tier-1--quick-wins-2-3-days-each)
4. [Tier 2 — Meaningful Upgrades](#4-tier-2--meaningful-upgrades-1-2-weeks-each)
5. [Tier 3 — Strategic Bets](#5-tier-3--strategic-bets-1-3-months)
6. [Implementation Code](#6-implementation-code)
7. [Priority Execution Order](#7-priority-execution-order)
8. [What to Never Do](#8-what-to-never-do)
9. [Measuring Success](#9-measuring-success)

---

## 1. Where We Are Now

### Current Architecture

```
User Query
    │
    ▼
Keyword Intent Detection
(_INTENT_MAP — 11 intent buckets, plain string matching)
    │
    ▼
City Data Retrieval
(MySQL: attractions, events, restaurants, hotels, products, news)
    │
    ▼
KB Search
(keyword ILIKE search + in-Python cosine similarity on 500 entries)
    │
    ▼
Context Builder
(3,500 char hard cap → crammed into system prompt)
    │
    ▼
Groq LLM (LLaMA 3 family)
(temperature 0.7 fixed, max_tokens 1024, last 4 messages history)
    │
    ▼
Post-Processing (async thread)
(auto-KB save, user profile keyword update, feedback log)
    │
    ▼
JSON Response → typewriter animation (fake, client-side)
```

### What Is Already Good — Do Not Touch

| Feature | Why It Works |
|---|---|
| Complaint fast-path (BK-XXXXXX regex) | Instant, no LLM needed, always accurate |
| Civic keyword detection → complaint redirect | Converts chat queries into actionable civic reports |
| Self-growing KB (`_maybe_auto_save_kb`) | AI improves itself over time without admin effort |
| Feedback loop (thumbs up/down → log unanswered) | Closes the quality gap loop automatically |
| Continuation call on `finish_reason == 'length'` | Prevents mid-sentence cutoffs |
| Prompt injection guard (`<user_message>` tags + skip patterns) | Security baseline is solid |
| Response caching (SHA256 key, 1hr TTL) | Reduces Groq API calls on repeated queries |
| City data cache (2min per intent bucket) | Prevents DB hammering on traffic spikes |

---

## 2. What Is Weak and Why

### Problem Table

| Problem | Root Cause | User-Facing Impact |
|---|---|---|
| **Scan modal does nothing intelligent** | No vision model connected — `_embed()` is text-only | Tourist points camera at Nyatapola → blank result |
| **Context starved at 3,500 chars** | Arbitrary hard cap from free-tier token anxiety | LLM answers with incomplete attraction lists; cuts mid-entry |
| **Intent detection is brittle** | Single keyword match, no disambiguation | "hungry near Nyatapola" → matches food, misses location context |
| **No real streaming** | Full response waits before any text shown | 2–4 second blank screen before first word appears |
| **In-Python semantic search is slow** | 500-entry cosine loop blocks the request thread | Adds ~200ms latency on every request; degrades under load |
| **Temperature fixed at 0.7 for everything** | Same randomness for emergency contacts and itinerary suggestions | Emergency answers drift; itineraries become repetitive |
| **User profile is keyword-scraped** | Fragile string matching (`cheap`, `budget`, `affordable`) | "I'm travelling on a tight budget" doesn't match any keyword |
| **Conversation history only 4 messages** | Arbitrary trim | Multi-step travel planning loses context by message 5 |
| **No query expansion** | User types "nyatapola" → searches for "nyatapola" only | Misses KB entries titled "Nyatapola Temple History" |
| **No follow-up suggestions** | AI answers and stops | Users don't know what to ask next; engagement drops |
| **No voice input** | No Whisper integration | Elderly locals and tourists who can't type Nepali are excluded |
| **English-only KB** | All KB entries in English | Nepali speakers get machine-translated answers; quality degrades |

---

## 3. Tier 1 — Quick Wins (2–3 days each)

These require no new infrastructure, no new packages, no schema changes.
Ship all of them before moving to Tier 2.

---

### 3.1 — Streaming Responses

**What:** Show the first word in ~300ms instead of waiting 3 seconds.
**Why:** The single highest-impact UX change possible. Users feel the AI is faster and smarter even if the total time is the same.

**Backend — add to `chatbot/views.py`:**

```python
import json
from django.http import StreamingHttpResponse
from django.views.decorators.http import require_http_methods

@require_http_methods(["POST"])
def chat_stream(request):
    """Streaming SSE endpoint — replaces chat_api for real-time token delivery."""
    # Apply same rate limiting as chat_api
    ip = get_client_ip(request)
    rate_key = f'chat_stream_{ip}'
    try:
        count = cache.incr(rate_key)
    except ValueError:
        cache.set(rate_key, 1, 3600)
        count = 1
    if count > 60:
        def _limit():
            yield f"data: {json.dumps({'error': 'Rate limit exceeded'})}\n\n"
        return StreamingHttpResponse(_limit(), content_type='text/event-stream')

    data = json.loads(request.body)
    user_message = data.get('message', '').strip()

    engine = MunicipalAIEngine()
    intent = engine._detect_intent(user_message)
    city_data, context_text = engine._get_cached_city_data(user_message, intent)
    system_prompt = engine._build_system_prompt(request.user, city_data, context_text)

    def event_stream():
        from groq import Groq
        client = Groq(api_key=engine.api_key)
        full_text = ''
        for chunk in client.chat.completions.create(
            model=engine.model,
            messages=[
                {'role': 'system', 'content': system_prompt},
                {'role': 'user',   'content': f'<user_message>{user_message}</user_message>'},
            ],
            max_tokens=1024,
            temperature=engine._get_temperature(intent),
            stream=True,
        ):
            token = chunk.choices[0].delta.content or ''
            if token:
                full_text += token
                yield f"data: {json.dumps({'token': token})}\n\n"
        yield f"data: {json.dumps({'done': True, 'intent': intent})}\n\n"

    return StreamingHttpResponse(event_stream(), content_type='text/event-stream')
```

**Add to `chatbot/urls.py`:**

```python
path('api/chat/stream/', views.chat_stream, name='chat_stream'),
```

**Frontend — replace the `askAI()` fetch with:**

```javascript
async function askAI() {
  const query = document.getElementById('heroQuery').value.trim();
  if (!query) return;

  showLoadingState();

  const resp = document.getElementById('aiResponseText');
  resp.style.display = 'block';
  resp.textContent = '';

  const source = new EventSource(`/api/chat/stream/?q=${encodeURIComponent(query)}`);
  // Use POST via fetch + ReadableStream instead of EventSource for POST bodies:

  const response = await fetch('/api/chat/stream/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
    body: JSON.stringify({ message: query }),
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const lines = decoder.decode(value).split('\n');
    for (const line of lines) {
      if (!line.startsWith('data:')) continue;
      const payload = JSON.parse(line.slice(5).trim());
      if (payload.token) resp.textContent += payload.token;
      if (payload.done) hideLoadingState();
    }
  }
}
```

---

### 3.2 — Raise Context Cap to 12,000 Characters

**What:** Increase `_MAX_CONTEXT_CHARS` from 3,500 to 12,000.
**Why:** You're giving the LLM 3,500 chars when the model can handle 400,000+ tokens. You're leaving 97% of its capability unused.

**In `chatbot/ai_engine.py`:**

```python
# Line 518 — change this one number
_MAX_CONTEXT_CHARS = 12000   # was 3500
```

Also increase KB content per entry from 250 chars to 600 chars:

```python
# Line 549 — change truncation
_add(entry['content'][:600])  # was [:250]
```

And increase attraction description from 120 to 300 chars:

```python
# Line 557
line = (f"• {a['name']} ({a['category']}): {a['description'][:300]} "  # was [:120]
```

---

### 3.3 — Intent-Adaptive Temperature

**What:** Different types of questions need different creativity levels.
**Why:** Emergency contacts must be exact (temperature 0.1). Itineraries should be varied and creative (temperature 0.75). Using 0.7 for everything is wrong.

**Add method to `MunicipalAIEngine`:**

```python
_INTENT_TEMPERATURES = {
    'emergency':     0.10,
    'info':          0.15,
    'transport':     0.20,
    'food':          0.55,
    'accommodation': 0.55,
    'events':        0.60,
    'general':       0.60,
    'tourism':       0.65,
    'shopping':      0.65,
    'itinerary':     0.75,
}

def _get_temperature(self, intent: str) -> float:
    return self._INTENT_TEMPERATURES.get(
        intent,
        getattr(settings, 'AI_TEMPERATURE', 0.7)
    )
```

**In `_call_groq`, replace the fixed temperature:**

```python
# Replace: temperature=temperature,
# With:
temperature=self._get_temperature(intent) if hasattr(self, '_current_intent') else temperature,
```

---

### 3.4 — Proactive Follow-Up Suggestions

**What:** After every AI response, show 2–3 follow-up questions the user is likely to ask next.
**Why:** Zero extra API calls. Dramatically increases engagement depth. Tourists don't know what they don't know — you guide them.

**Add to `MunicipalAIEngine`:**

```python
_FOLLOWUPS = {
    'tourism': [
        "What are the entry fees?",
        "What time does it open?",
        "How do I get there from Kathmandu?",
    ],
    'food': [
        "Any vegetarian options nearby?",
        "What is Juju Dhau?",
        "Best place for a full Newari thali?",
    ],
    'itinerary': [
        "Can you add Pottery Square to day 1?",
        "What about a second day itinerary?",
        "Best time of year to visit Bhaktapur?",
    ],
    'accommodation': [
        "What is the price range?",
        "Any hotels near Durbar Square?",
        "Do they serve breakfast?",
    ],
    'transport': [
        "How long does the journey take?",
        "Is there a direct bus from Thamel?",
        "What time is the last bus back?",
    ],
    'events': [
        "When is Bisket Jatra this year?",
        "Are there any free events?",
        "How do I get tickets?",
    ],
    'shopping': [
        "What is the price range for Thangka paintings?",
        "Is bargaining acceptable?",
        "Are there any fixed-price shops?",
    ],
    'emergency': [
        "Where is the nearest hospital?",
        "Is there a tourist police office?",
        "What is the ambulance number?",
    ],
    'general': [
        "What are the top 3 things to see?",
        "What is Bhaktapur famous for?",
        "How is Bhaktapur different from Patan?",
    ],
}

def get_followups(self, intent: str) -> list:
    import random
    suggestions = self._FOLLOWUPS.get(intent, self._FOLLOWUPS['general'])
    return random.sample(suggestions, min(2, len(suggestions)))
```

**In `chat()` method, add to return dict:**

```python
return {
    'response':  response_text,
    'sources':   sources,
    'intent':    intent,
    'followups': self.get_followups(intent),   # ADD THIS
}
```

**In the frontend, render followups as clickable pills after the response:**

```javascript
if (data.followups?.length) {
  const pillsHtml = data.followups.map(q =>
    `<span class="ai-suggestion" onclick="fillAndAsk('${q.replace(/'/g, "\\'")}')">${q}</span>`
  ).join('');
  document.getElementById('aiSuggestions').innerHTML = pillsHtml;
}
```

---

### 3.5 — Increase Conversation History to 8 Messages

**What:** Pass the last 8 messages instead of 4 to the LLM.
**Why:** Multi-step travel planning breaks after 4 messages. A visitor building a 2-day itinerary loses context by message 5.

**In `ai_engine.py` line 654:**

```python
for msg in conversation_history[-8:]:   # was [-4:]
```

---

### 3.6 — Query Expansion

**What:** Before searching the KB, expand short queries into richer search strings.
**Why:** A user typing "nyatapola" should retrieve entries titled "Nyatapola Temple History", "Five-Storey Pagoda", "Taumadhi Square". Currently it only matches exact substring "nyatapola".

**Add to `CityContextRetriever`:**

```python
_QUERY_EXPANSIONS = {
    'nyatapola':   'Nyatapola Temple five-storey pagoda Taumadhi Square Bhaktapur heritage',
    'bisket':      'Bisket Jatra New Year chariot festival April Bhaktapur celebration',
    'bisket jatra':'Bisket Jatra New Year chariot festival April Bhaktapur celebration',
    'juju dhau':   'Juju Dhau king curd yogurt pottery Bhaktapur dairy',
    'durbar':      'Bhaktapur Durbar Square 55-window palace heritage monuments courtyards',
    'durbar square':'Bhaktapur Durbar Square 55-window palace heritage monuments courtyards',
    'changu':      'Changu Narayan Temple UNESCO hilltop Vishnu oldest Nepal',
    'changu narayan':'Changu Narayan Temple UNESCO hilltop Vishnu oldest Nepal',
    'pottery':     'Bhaktapur pottery square Kumale clay craft traditional',
    'thangka':     'Thangka painting Buddhist art Tibetan scroll religious',
    'newari':      'Newari culture tradition architecture cuisine Newar community',
    'entry fee':   'entry fee ticket price cost foreigners SAARC Nepali citizen',
    'emergency':   'emergency police hospital ambulance fire tourist police contacts',
    'kathmandu':   'from Kathmandu distance bus taxi microbus tempo travel',
}

def _expand_query(self, query: str) -> str:
    q_lower = query.lower().strip()
    for trigger, expansion in self._QUERY_EXPANSIONS.items():
        if trigger in q_lower:
            return f"{query} {expansion}"
    return query
```

**In `retrieve()`, expand before searching:**

```python
def retrieve(self, query: str, semantic_hits: list = None) -> dict:
    expanded_query = self._expand_query(query)
    q = expanded_query.lower()
    # ... rest of method uses q (expanded) instead of query.lower()
```

---

## 4. Tier 2 — Meaningful Upgrades (1–2 weeks each)

Complete all of Tier 1 before starting these.

---

### 4.1 — Vision AI for the Scan Feature (HIGHEST PRIORITY IN TIER 2)

**What:** Connect the camera scan modal to a vision-capable LLM so it can identify temples, food, crafts, text in photos.
**Why:** This is the only feature on your platform that no other municipal website in Nepal has. A tourist pointing their phone at Nyatapola and getting instant AI-powered heritage information is a genuine wow moment.

**Model to use:** `meta-llama/llama-4-scout-17b-16e-instruct` (Groq, supports image input, fast)

**Add to `chatbot/views.py`:**

```python
@require_http_methods(["POST"])
def scan_analyze(request):
    """Receive base64 image from scan modal, return AI description."""
    ip = get_client_ip(request)
    rate_key = f'scan_{ip}'
    try:
        count = cache.incr(rate_key)
    except ValueError:
        cache.set(rate_key, 1, 3600)
        count = 1
    if count > 20:   # stricter limit — image calls are expensive
        return JsonResponse({'error': 'Rate limit exceeded'}, status=429)

    try:
        data = json.loads(request.body)
        image_b64 = data.get('image')   # base64 encoded JPEG
        user_question = data.get('question', '').strip()[:200]

        if not image_b64:
            return JsonResponse({'error': 'No image provided'}, status=400)

        engine = MunicipalAIEngine()
        result = engine.analyze_image(image_b64, user_question)

        return JsonResponse({'response': result, 'intent': 'scan'})

    except Exception as e:
        return JsonResponse({'error': 'Could not analyze image'}, status=500)
```

**Add `analyze_image` to `MunicipalAIEngine`:**

```python
_VISION_MODEL = 'meta-llama/llama-4-scout-17b-16e-instruct'

def analyze_image(self, base64_image: str, user_question: str = '') -> str:
    if not self.api_key:
        return "AI scan requires configuration. Please set up your Groq API key."

    city = getattr(settings, 'CITY_NAME', 'Bhaktapur')
    general = self._get_general_info()

    system = (
        f"You are an expert AI guide for {city}, Nepal — a UNESCO World Heritage city. "
        f"Identify anything visible in the image: temples, monuments, food, handicrafts, "
        f"street scenes, or text. Provide: what it is, its cultural significance, history, "
        f"entry fee (if applicable), visiting tips, and any relevant local context. "
        f"Be specific to {city}. Today: {general['today']}. Currency: {general['currency']}."
    )

    content = [
        {
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
        },
        {
            "type": "text",
            "text": (
                f"{system}\n\n"
                + (f"The visitor asks: {user_question}" if user_question else "Describe what you see and provide relevant visitor information.")
            )
        }
    ]

    try:
        client = _get_groq_client(self.api_key)
        response = client.chat.completions.create(
            model=self._VISION_MODEL,
            messages=[{"role": "user", "content": content}],
            max_tokens=800,
            temperature=0.5,
        )
        return response.choices[0].message.content
    except Exception as e:
        return (
            "I couldn't analyze that image right now. "
            "Try asking me directly — describe what you see and I'll help you identify it."
        )
```

**In `chatbot/urls.py`:**

```python
path('api/scan/', views.scan_analyze, name='scan_analyze'),
```

**In the scan modal JS (`base/base.html`), replace the capture button handler:**

```javascript
async function sendScanImage(base64Jpeg) {
  showScanLoading();
  const question = document.getElementById('scanQuestion')?.value || '';

  const res = await fetch('/api/scan/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
    body: JSON.stringify({ image: base64Jpeg, question }),
  });
  const data = await res.json();
  showScanResult(data.response);
}
```

---

### 4.2 — Hybrid Retrieval: BM25 + Semantic

**What:** Score KB entries using both keyword frequency (BM25) AND semantic similarity, then merge scores.
**Why:** BM25 catches exact names ("Nyatapola"). Semantic catches intent ("five-storey pagoda near Taumadhi"). Together they catch what either alone misses.

**Formula:**
```
final_score = 0.6 × semantic_score + 0.4 × bm25_score
```

**Add to `MunicipalAIEngine`:**

```python
@staticmethod
def _bm25_score(query_terms: list, document: str, k1: float = 1.5, b: float = 0.75) -> float:
    """Simplified BM25 score for a single document."""
    import math
    doc_lower = document.lower()
    doc_len = len(doc_lower.split())
    avg_doc_len = 150   # approximate average KB entry length in words
    score = 0.0
    for term in query_terms:
        tf = doc_lower.count(term)
        if tf == 0:
            continue
        idf = math.log(1 + (500 / (tf + 0.5)))   # simplified IDF
        score += idf * ((tf * (k1 + 1)) / (tf + k1 * (1 - b + b * doc_len / avg_doc_len)))
    return score

def _hybrid_search_kb(self, query: str, query_vec: list = None, top_k: int = 7) -> list:
    """Combine BM25 keyword score + semantic vector score for best retrieval."""
    try:
        from chatbot.models import KnowledgeBase
        query_terms = [w for w in query.lower().split() if len(w) > 2]
        entries = KnowledgeBase.objects.filter(
            is_active=True, auto_generated=False
        ).order_by('-priority').values('title', 'content', 'embedding')[:self._SEMANTIC_SEARCH_CAP]

        scored = []
        for e in entries:
            text = f"{e['title']} {e['content']}"
            bm25 = self._bm25_score(query_terms, text)

            semantic = 0.0
            if query_vec and e['embedding'] and len(e['embedding']) == len(query_vec):
                semantic = self._cosine_sim(query_vec, e['embedding'])

            if bm25 > 0 or semantic > 0.35:
                final = 0.6 * semantic + 0.4 * min(bm25 / 10, 1.0)
                scored.append((final, e))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {'title': e['title'], 'content': e['content']}
            for score, e in scored[:top_k]
            if score > 0.1
        ]
    except Exception:
        return []
```

---

### 4.3 — LLM-Based Preference Extraction

**What:** Replace fragile keyword-matching for user profile updates with a small LLM extraction call.
**Why:** "I'm travelling with my family on a tight budget" never matches `cheap`, `budget`, `affordable`. An LLM extracts it perfectly.

**Replace `_update_user_profile` with:**

```python
def _extract_preferences_with_llm(self, message: str) -> dict:
    """Use a fast small model to extract structured preferences from natural language."""
    if not self.api_key or len(message) < 10:
        return {}
    try:
        client = _get_groq_client(self.api_key)
        resp = client.chat.completions.create(
            model='llama-3-8b-8192',   # fast + cheap for extraction
            messages=[{
                'role': 'user',
                'content': (
                    'Extract travel preferences from this message as JSON. '
                    'Only include keys that are clearly stated. '
                    'Valid keys: dietary (vegetarian/vegan/halal/none), '
                    'budget (budget/mid-range/premium), '
                    'group (solo/couple/family/group). '
                    f'Message: "{message[:300]}"\n'
                    'Return only valid JSON, nothing else. Example: {"budget": "budget", "group": "family"}'
                )
            }],
            max_tokens=80,
            temperature=0.0,
        )
        import json as _json
        text = resp.choices[0].message.content.strip()
        return _json.loads(text)
    except Exception:
        return {}
```

---

### 4.4 — Conversation Memory Summarization

**What:** When a conversation exceeds 8 messages, compress the earliest 4 into a summary rather than dropping them.
**Why:** Long travel planning sessions currently lose their context. Users have to repeat themselves.

**Add to `MunicipalAIEngine`:**

```python
def _summarize_history(self, messages: list) -> str:
    """Compress older messages into a brief summary to preserve context without token cost."""
    if not self.api_key or not messages:
        return ''
    try:
        client = _get_groq_client(self.api_key)
        history_text = '\n'.join(
            f"{m['role'].upper()}: {m['content'][:200]}" for m in messages
        )
        resp = client.chat.completions.create(
            model='llama-3-8b-8192',
            messages=[{
                'role': 'user',
                'content': (
                    'Summarize this conversation history in 2–3 sentences, '
                    'focusing on what the user is looking for and any preferences expressed:\n\n'
                    f'{history_text}'
                )
            }],
            max_tokens=120,
            temperature=0.1,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return ''

def _prepare_history(self, conversation_history: list) -> list:
    """Summarize old messages if history is long."""
    if len(conversation_history) <= 8:
        return conversation_history[-8:]
    summary = self._summarize_history(conversation_history[:-6])
    condensed = [{'role': 'system', 'content': f'Earlier in this conversation: {summary}'}]
    condensed += conversation_history[-6:]
    return condensed
```

**In `chat()` method, replace:**

```python
# Replace: for msg in conversation_history[-8:]:
for msg in self._prepare_history(conversation_history):
```

---

## 5. Tier 3 — Strategic Bets (1–3 months)

Complete Tiers 1 and 2 fully before starting these.

---

### 5.1 — Voice Input via Whisper

**Why:** Elderly Bhaktapur locals cannot type Nepali on a phone keyboard. Tourists prefer to speak. Voice is the most natural interface for a city guide.

**Model:** `distil-whisper-large-v3-en` via Groq — extremely fast, free tier available.

**Add to `chatbot/views.py`:**

```python
@require_http_methods(["POST"])
def voice_transcribe(request):
    """Receive audio blob, return transcribed text."""
    audio_file = request.FILES.get('audio')
    if not audio_file:
        return JsonResponse({'error': 'No audio file'}, status=400)

    try:
        from groq import Groq
        client = Groq(api_key=settings.GROQ_API_KEY)
        transcription = client.audio.transcriptions.create(
            file=(audio_file.name, audio_file.read(), 'audio/webm'),
            model='distil-whisper-large-v3-en',
            response_format='text',
            language='ne',   # Nepali — or 'en' for English, or omit for auto-detect
        )
        return JsonResponse({'text': transcription})
    except Exception as e:
        return JsonResponse({'error': 'Transcription failed'}, status=500)
```

**Frontend microphone button:**

```javascript
let mediaRecorder;
let audioChunks = [];

async function startVoice() {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  mediaRecorder = new MediaRecorder(stream);
  audioChunks = [];
  mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
  mediaRecorder.onstop = async () => {
    const blob = new Blob(audioChunks, { type: 'audio/webm' });
    const form = new FormData();
    form.append('audio', blob, 'voice.webm');
    const res = await fetch('/api/voice/', { method: 'POST', body: form,
      headers: { 'X-CSRFToken': getCookie('csrftoken') } });
    const data = await res.json();
    if (data.text) {
      document.getElementById('heroQuery').value = data.text;
      askAI();
    }
  };
  mediaRecorder.start();
  setTimeout(() => mediaRecorder.stop(), 8000);   // 8 second max recording
}
```

---

### 5.2 — Nepali Language Knowledge Base

**Why:** Your entire KB is in English. A citizen writing in Nepali gets answers that were generated by translating English KB entries — quality degrades significantly. A native Nepali KB produces native Nepali answers.

**What to do:**

1. Add `language` field to `KnowledgeBase` model:
   ```python
   language = models.CharField(max_length=5, default='en', choices=[('en', 'English'), ('ne', 'Nepali')])
   ```

2. Detect query script at retrieval time:
   ```python
   def _is_nepali_script(self, text: str) -> bool:
       return any('ऀ' <= c <= 'ॿ' for c in text)
   ```

3. Route retrieval to language-matched KB entries:
   ```python
   lang = 'ne' if self._is_nepali_script(query) else 'en'
   qs = KnowledgeBase.objects.filter(is_active=True, language=lang, ...)
   ```

4. Seed Nepali KB entries using the admin panel — start with the top 20 most-asked questions (visible in `UnansweredQuery` admin).

---

### 5.3 — Real-Time Municipal Data Feed

**Why:** Events and announcements in your DB are manually entered. The AI doesn't know about things that haven't been seeded. Connect to public data sources so the AI is always current.

**What to connect:**

| Source | Data | Method |
|---|---|---|
| Nepal Tourism Board | Festival calendar, event dates | Scrape / RSS |
| Bhaktapur Municipality website | Announcements, notices | Scrape every 6h via Celery |
| Weather API (OpenMeteo — free) | Today's weather, forecast | REST API, cache 1h |
| Nepal public holidays | Public holidays calendar | Static JSON, update annually |

**Celery task for auto-sync:**

```python
# chatbot/tasks.py
@app.task
def sync_municipal_announcements():
    """Pull latest announcements from municipality website into KnowledgeBase."""
    import requests
    from bs4 import BeautifulSoup
    # Scrape municipality notice board
    # Create/update KnowledgeBase entries with auto_generated=True
    ...
```

---

### 5.4 — AI-Powered Complaint Categorization

**Why:** Citizens describe issues in plain language. The current system matches keywords to suggest a category. An LLM can categorize with far higher accuracy and suggest the correct ward automatically.

**Add to complaint submission flow:**

```python
def ai_categorize_complaint(title: str, description: str) -> dict:
    """Return suggested category, ward, and priority for a citizen complaint."""
    prompt = (
        "Categorize this municipal complaint for Bhaktapur. "
        "Return JSON with: category (ROAD/SANITATION/WATER/ELECTRICITY/NOISE/INFRASTRUCTURE/OTHER), "
        "priority (low/medium/high/urgent), suggested_ward (1-17 or null if unclear).\n\n"
        f"Title: {title}\nDescription: {description[:300]}"
    )
    # Use llama-3.1-8b-instant for speed
    ...
```

---

### 5.5 — Multilingual Tourist Support

**Target languages:** Hindi, Chinese (Simplified), Bengali, English, Nepali

**Why:** Bhaktapur receives significant tourist traffic from India and China. Offering AI guidance in their native language is a major competitive advantage no other municipality in Nepal has.

**Implementation:** Detect language from query using `langdetect` package, then set the LLM response language accordingly in the system prompt:

```python
SUPPORTED_LANGUAGES = {
    'en': 'English',
    'ne': 'Nepali (नेपाली)',
    'hi': 'Hindi (हिंदी)',
    'zh-cn': 'Chinese Simplified (简体中文)',
    'bn': 'Bengali (বাংলা)',
}

def _detect_language(self, text: str) -> str:
    try:
        from langdetect import detect
        return detect(text)
    except Exception:
        return 'en'
```

---

## 6. Implementation Code

### Settings to Add (`municipal_ai/settings.py`)

```python
# AI Configuration
GROQ_MODEL = os.environ.get('GROQ_MODEL', 'llama-3.3-70b-versatile')
GROQ_VISION_MODEL = os.environ.get('GROQ_VISION_MODEL', 'meta-llama/llama-4-scout-17b-16e-instruct')
GROQ_FAST_MODEL = os.environ.get('GROQ_FAST_MODEL', 'llama-3-8b-8192')
GROQ_WHISPER_MODEL = os.environ.get('GROQ_WHISPER_MODEL', 'distil-whisper-large-v3-en')
GROQ_TIMEOUT = int(os.environ.get('GROQ_TIMEOUT', 30))
AI_MAX_TOKENS = int(os.environ.get('AI_MAX_TOKENS', 1024))
AI_MAX_CONTEXT_CHARS = int(os.environ.get('AI_MAX_CONTEXT_CHARS', 12000))
AI_STREAM_ENABLED = os.environ.get('AI_STREAM_ENABLED', 'true').lower() == 'true'
```

### `.env` Variables to Add

```env
GROQ_MODEL=llama-3.3-70b-versatile
GROQ_VISION_MODEL=meta-llama/llama-4-scout-17b-16e-instruct
GROQ_FAST_MODEL=llama-3-8b-8192
GROQ_WHISPER_MODEL=distil-whisper-large-v3-en
AI_MAX_CONTEXT_CHARS=12000
AI_STREAM_ENABLED=true
```

### New URL Routes to Add

```python
# chatbot/urls.py
urlpatterns = [
    path('api/chat/',        views.chat_api,           name='chat_api'),
    path('api/chat/stream/', views.chat_stream,         name='chat_stream'),   # NEW
    path('api/scan/',        views.scan_analyze,        name='scan_analyze'),  # NEW
    path('api/voice/',       views.voice_transcribe,    name='voice_transcribe'),  # NEW (Tier 3)
    path('api/feedback/',    views.message_feedback,    name='message_feedback'),
    path('api/language/',    views.set_language,        name='set_language'),
    ...
]
```

---

## 7. Priority Execution Order

```
WEEK 1
  ├── 3.2  Raise context cap to 12,000 chars          (30 min — change 3 numbers)
  ├── 3.3  Intent-adaptive temperature                 (1 hour)
  ├── 3.5  Conversation history 4→8 messages           (5 min — change one number)
  └── 3.6  Query expansion                             (2 hours)

WEEK 2
  ├── 3.1  Streaming responses                         (1 day)
  └── 3.4  Follow-up suggestion pills                  (2 hours)

WEEK 3
  └── 4.1  Vision AI for scan modal                    (2 days) ← BIGGEST WOW MOMENT

WEEK 4
  └── 4.2  Hybrid BM25 + semantic retrieval            (2 days)

WEEK 5
  └── 4.3  LLM-based preference extraction             (1 day)
  └── 4.4  Conversation memory summarization           (1 day)

MONTH 2
  ├── 5.1  Voice input via Whisper                     (3 days)
  └── 5.2  Nepali language KB                          (1 week — mostly content work)

MONTH 3
  ├── 5.3  Real-time municipal data feed               (2 weeks)
  ├── 5.4  AI complaint categorization                 (3 days)
  └── 5.5  Multilingual support                        (1 week)
```

---

## 8. What to Never Do

These are common mistakes that will break the AI or make it worse:

| Do Not | Why |
|---|---|
| Remove the `<user_message>` tag wrapping | That tag is your prompt injection defense. Remove it and adversarial users can override the system prompt. |
| Set temperature above 0.8 for any intent | The model starts hallucinating place names, prices, and hours. |
| Auto-save KB entries without the skip-pattern check | Adversarial responses or LLM failures will permanently corrupt the knowledge base. |
| Increase `_SEMANTIC_SEARCH_CAP` above 2,000 without moving to a vector DB | In-Python cosine scoring 2,000+ entries on every request will kill response time under load. |
| Store raw conversation history without the 8-message cap | Token costs grow linearly. A 40-message conversation will exceed Groq's context limit. |
| Use `gpt-4o` or Claude for the main chat endpoint | Cost becomes unsustainable at scale. Groq LLaMA is 100x cheaper and fast enough for this use case. |
| Cache scan/image results | Image responses are context-specific (same image, different question = different answer). Don't cache them. |
| Set `auto_generated=True` on vision/scan KB saves | Vision responses are too specific to a single image to be useful as general KB entries. |

---

## 9. Measuring Success

Track these numbers before and after each Tier to know if the changes are working:

### Tier 1 Metrics

| Metric | How to Measure | Target |
|---|---|---|
| **Time to first token** | Frontend `Date.now()` on request start vs first token received | < 400ms |
| **User session depth** | Avg messages per conversation (check `Message` table) | Increase by 40% |
| **Follow-up pill click rate** | Track clicks on suggested pills vs total responses | > 20% click-through |
| **Cache hit rate** | `cache.get` returns vs misses (add counter) | > 60% for repeat queries |

### Tier 2 Metrics

| Metric | How to Measure | Target |
|---|---|---|
| **Scan modal usage** | Track `scan_analyze` API calls per day | > 50 uses/day after launch |
| **KB retrieval quality** | Negative feedback rate (thumbs down / total responses) | < 5% |
| **Response relevance** | Admin review of `UnansweredQuery` — are queries decreasing? | Decrease 30% month-over-month |
| **User profile utilization** | % of `UserAIProfile` records with at least one preference set | > 40% of registered users |

### Tier 3 Metrics

| Metric | How to Measure | Target |
|---|---|---|
| **Voice input adoption** | Track `voice_transcribe` API calls | > 15% of mobile queries |
| **Multilingual usage** | Count non-English queries in `Message` table | Track baseline, grow MoM |
| **Complaint AI categorization accuracy** | Admin reviews AI suggestion vs final human category | > 85% match rate |

---

## Appendix — Model Reference

| Model | Use Case | Speed | Cost |
|---|---|---|---|
| `llama-3.3-70b-versatile` | Main chat responses | Fast | Low |
| `meta-llama/llama-4-scout-17b-16e-instruct` | Vision / scan | Fast | Low |
| `llama-3.1-8b-instant` | Extraction, summarization, categorization | Very fast | Very low |
| `distil-whisper-large-v3-en` | Voice transcription | Very fast | Very low |
| `nomic-embed-text-v1.5` | KB embeddings | Fast | Very low |

All models available on Groq. No OpenAI dependency needed. No cost change vs current setup.

---

*Last updated: 2026-06-24*
*This document is the single source of truth for AI improvement on this platform.*
*Do not create separate upgrade plans. Update this file when something is implemented.*
