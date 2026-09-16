# Fallback brain — findings

What the assistant does when Groq is unavailable (quota exhausted, outage,
circuit breaker open). Tested by forcing the circuit open rather than by
burning real quota, which would have cost money and taken the live site
down for actual users.

_Run against the deployed build. Update the date and commit when re-run._

- Date: 2026-09-16
- Commit: see `git log -1` at time of run
- Method: `open_circuit()` then queries as tourist / citizen / official / admin

---

## Headline

**7 of 10 questions are answered with Groq completely unavailable.** The
tool layer *is* the fallback brain — it reads municipal records directly and
never calls a model. Groq is only needed for open-ended generation.

| Persona | Question | Served without Groq |
|---|---|---|
| Tourist | entry fees for Durbar Square | yes — attractions |
| Tourist | where to eat near Durbar Square | yes — businesses |
| Tourist | plan me a two day trip | no — generative |
| Citizen | how much is the business tax | yes — आर्थिक ऐन 2083/084 |
| Citizen | व्यवसाय कर कति हो? | yes — आर्थिक ऐन 2083/084 |
| Citizen | documents for citizenship recommendation | yes — नागरिक वडापत्र |
| Citizen | there is a pothole on my street | yes — complaint filing |
| Citizen | show me public notices | yes — notices |
| Official | how many complaints are pending | no — no staff tools exist |
| Admin | show all users | no — no admin tools exist |

---

## Three defects found and fixed

### 1. The fallback never saw the municipal documents

`LocalRetrieverAdapter` wrapped only the legacy keyword retriever, so the
imported charter and tax Act were invisible to it. Questions those documents
answer came back as "no information".

Fixed: the adapter now searches the same index the tools use, and those hits
rank first.

### 2. Unrelated content was served as municipal record

"How many complaints are pending" returned **Bisket Jatra festival text**
under the heading *"Based on our municipal records"*. "Show all users"
returned visitor entry fees.

The relevance gate was an 8% lexical overlap — a bar almost nothing fails.
It was also one-directional, so it rejected the tax Act for an English
question *about the tax Act*.

Fixed: the gate now measures how much of the question a passage actually
addresses, across both languages, at the same 0.35 bar the tools use. Both
questions above now return the honest "I don't have confident information"
message instead of a wrong one.

### 3. Filler words were counted as content

"Tell me about Nyatapola" scored 0.33 against a passage titled *Nyatapola
Temple*, because "tell" and "about" counted as content words. The threshold
was right; the vocabulary was wrong. Conversational filler is now excluded
in both languages.

---

## Open gaps

1. **Officials and admins have no tools.** Staff intelligence was
   deliberately deferred. Today an official asking "how many complaints are
   pending" gets a generated answer — a fabricated number about municipal
   operations, which is worse than no answer. With Groq down they now
   correctly get "no information". A read-only staff tool set would fix
   both.

2. **Self-learning writes into the knowledge base but is not used.**
   `_maybe_auto_save_kb` has written 5 entries since the rebuild. They are
   excluded from retrieval on purpose: at one point 67% of the knowledge
   base was the assistant's own prior output being cited back as municipal
   record. Any learning loop must keep that separation — see below.

3. **The generative path still invents specifics.** Answers not served by a
   tool are labelled "written by the assistant", but the label is the only
   safeguard.

---

## Proposed design for a learning fallback

Learning is worth having, but not by writing generated text into the same
store as the charter. Two tiers, never merged:

- **Tier 1 — authoritative.** Charter, tax Act, notices, seeded city data.
  Human-published. Quoted verbatim, cited with its fiscal year. Never
  written by the assistant.
- **Tier 2 — learned.** Answers the assistant produced that a citizen marked
  helpful. Used **only** when Groq is unavailable *and* Tier 1 has no match.
  Always labelled as previously-generated, never as municipal record.

The signal already exists: the chat has 👍/👎 buttons writing to
`MessageFeedback`. Promoting only thumbs-up answers into Tier 2 gives a
learning loop grounded in real usefulness rather than in the model's own
confidence.

**Built.** `promote_helpful_answers` turns 👍-rated answers into `FAQEntry`
rows; the fallback searches them after municipal documents and serves them
under "From an earlier answer that a resident marked helpful — not an
official municipal record". Refusals and errors are never promoted, and a
learned answer must cover at least half the question before it is offered.

Nothing has been promoted yet, because **no citizen has pressed 👍**:
`ResponseFeedback` is empty. The loop is wired but unfed.

---

## Free tier limits, measured

Read from Groq's own response headers:

| Limit | Value |
|---|---|
| Requests | 1,000 / day |
| Tokens | **8,000 / minute** |
| Token window reset | ~1 second |
| Request window reset | ~1 minute |

The binding constraint is tokens per minute, not requests per day. With
`AI_MAX_TOKENS = 1500` plus prompt context, that is roughly **two to four
generative answers per minute** before throttling — a handful of
simultaneous citizens.

This is why the tool layer matters more than the model: it answers from
municipal records at no token cost, so the questions that exhaust the quota
are only the open-ended ones.

---

# Retrieval: what the questions could not reach

Probing the assistant as a tourist found 7 of 18 questions unanswered. Only
three of those were missing content. The rest were material already indexed
that the words of a normal question could not reach.

## The matcher only stemmed one of its two languages

`_stem()` trimmed Nepali case endings and did nothing to English. So the
index held the words and the query held the same words in another form:

| Question | Indexed text | Matched |
|---|---|---|
| "where can I **eat**" | "avoid **eating** near temples" | no |
| "where can I eat" | "best **restaurants** near Durbar Square" | no |
| "building permit **fees**" | "**fee**" | no |
| "**taxes**" | "**tax**" | no |

`search()` has no minimum score — it returns anything scoring above zero — so
"where can I eat" returned *nothing at all*. Not a weak answer. Nothing,
against a chunk that names five local dishes and where to eat them.

English inflections are now trimmed the same way Nepali endings are. The
rule is deliberately crude, because both the question and the document go
through it: agreeing with itself matters more than being right about
English. `buses` → `buse` is wrong and still matches another `buses`.

## Nepali stemming did not converge, so the two forms never met

This was the older bug, and worse, because the tests claimed it was fixed.

```
नगरपालिकाको  → (strip को) → नगरपालिका     # stops here
नगरपालिका    → (strip का) → नगरपालि       # different answer
```

Stripping once meant a word's inflected and bare forms landed on different
strings. A question about the municipality could not reach a document naming
it — the exact failure the stemmer was written to prevent. The test asserted
`tokenize('नगरपालिकाको') == ['नगरपालिका']`, which passed while the property
that mattered was false.

Stemming now repeats to a fixed point, and the test asserts what the
docstring always claimed: that the two forms agree, not that either equals a
particular string.

## BM25 rank is not "answers the question"

With English stemming on, `घर नक्सा पास कसरी गर्ने` ("how do I get a house
map approved") started returning a hotel listing, because the listing
repeats a common word often and BM25 rewards that. The Act that sets the
building-permit fee was still retrieved — at rank two, with **twice** the
question's words covered.

`search()` now reconsiders its top 8 candidates by coverage before cutting
to `limit`. Across 28 probed questions this improved 2 and worsened none;
mean coverage 0.774 → 0.804.

## Synonyms buy reach and cost precision

Worth keeping only where measured. Two of the groups first written had to be
withdrawn:

| Group | Effect | Kept |
|---|---|---|
| stay/overnight/hotel → accommodation | "where to stay" 0.00 → 1.00 | yes |
| eat/food/dining → restaurant | "where can I eat" 0.00 → 1.00 | yes |
| wear/clothing/modest → dress | dress-code question 0.50 → 1.00 | yes |
| fee → **entry, ticket** | pulled the tourist entry-fee page over the Act on *any* fee question | **no** |
| temple → shrine, pagoda, monument | lifted temple-named pages over the page that answers | **no** |

This is the third time a synonym has cost more than it bought — `व्यवसाय` →
`shop` did it earlier by pulling a shopping guide above the tax Act. Every
group added here was checked in both directions before being kept.

## Still missing: content, not vocabulary

These return nothing because nothing is indexed. They are not retrieval
bugs and must not be filled with plausible text — a wrong toilet location or
an invented accessibility claim is worse than an honest refusal.

- public toilets
- ATMs / card payment / currency exchange
- wheelchair and step-free access
- solo-travel safety
- activities for children

Each needs a source from the municipality before it is written down.

---

# Contact details the assistant stated as fact

## A number nobody published

`+977-1-6610000` was in twelve places: complaint confirmations,
password-reset mail, marketplace order mail, dashboard notifications, seeded
knowledge, and the assistant's own reply when it has no answer. The
municipality publishes `977-01-6613957` and `977-01-6610096`, and nothing
else. The discrepancy only surfaced because `seed_official_contacts` had
already recorded the real ones with their source, so two different numbers
for one office existed side by side in the same database.

The no-answer reply was the worst placement. Someone who has already failed
to get an answer is exactly the person who will act on whatever it says
next. That reply also placed the office at Dattatreya Square — not published
either — and pointed an emergency at an office switchboard.

**Correcting the source files did not fix it.** The database had been seeded
from the old files, so three indexed chunks kept serving the number after
every `.py` was clean. `correct_contact_numbers` fixes stored rows and is
idempotent; `core/test_contacts` fails if the number reappears in source.

## The tourist police number was wrong too

Three entries listed `+977-1-4247041` as "Tourist Police Bhaktapur". The
Nepal Tourism Board publishes:

| | |
|---|---|
| Bhaktapur | 9851289448 |
| Nagarkot | 9851289447 |
| Toll free, nationwide | **1144** |

`4247041` is not in that list. The toll-free line — the one number a
visitor in trouble can actually remember — appeared nowhere in the app.

`Bhaktapur Hospital 01-6610798` checked out against independent sources.
Five numbers could not be verified either way and were left alone and
listed by the command, because deleting an emergency number leaves a visitor
with nothing and inventing one is worse.

Sources are now cited inline in the entry itself, so the next person to
doubt a number can check it without re-doing this.

## An English question got a Devanagari answer

`tourist police` returned the Nepali entry. That entry cites its source —
`ntb.gov.np/en/plan-your-trip/.../tourist-police` — and a URL tokenises into
English words, so it matched an English query exactly as well as the English
entry and won the tie.

Ranking is now coverage, then script agreement, then BM25. Script is a
tiebreaker and not a filter: a citizen asking in Nepali about something
documented only in English must still reach it.

Detecting the script by counting letters had the same bug in miniature — the
URL's letters outvoted the Nepali text in a short entry, so a *cited source*
made an entry look English. URLs are excluded before counting.
