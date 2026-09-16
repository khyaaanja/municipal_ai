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

**Not yet built.** Recorded here so the next pass starts from a decision
rather than from the current implicit behaviour.
