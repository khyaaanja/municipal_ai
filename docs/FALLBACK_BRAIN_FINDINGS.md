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

---

# Measuring the assistant instead of measuring retrieval

Probing `search()` directly had been scoring the wrong thing in both
directions. It counted a miss whenever the router was always going to
handle the message — "my street light is broken" files a complaint and
retrieves nothing — and counted a hit whenever a query merely shared a word,
as "do I need a guide" did against *Newari Cuisine Guide*.

`scripts/persona_probe.py` now goes through the path a real message takes:
router, then knowledge, then the no-answer reply. Every finding below came
from that and not from retrieval scores.

## Reporting a problem in Nepali failed at four separate steps

One message — "सडक बत्ती बिग्रियो", a broken street light — and every stage
mishandled it.

| Step | What happened |
|---|---|
| Category | Filed as **ROAD**. "सडक" (road) and "बत्ती" (light) both match, and the category was decided by dict order |
| Language | The entire conversation replied in English |
| Validation | Refused: 18 characters against a 20-character floor |
| Confirmation | "हो" **discarded the draft** |

The English phrasing was right only by accident: "street light" is one
ELECTRICITY phrase and "street" alone is not a ROAD keyword, so nothing
competed. `detect_category` now takes the longest matching keyword, which is
the more specific claim about the message in either language.

The character floor deserves its own note. Devanagari attaches vowels to the
consonant rather than setting them beside it, so it reaches the same content
in fewer codepoints. A flat minimum is therefore a *stricter* test in Nepali:
18 characters of Nepali said exactly what 25 characters of English said, and
only the Nepali was rejected. The floor exists to refuse one-word
non-descriptions, and 12 still refuses "बिग्रियो".

The confirmation bug was the worst of them. `AFFIRMATIVE` held romanised
Nepali but no Devanagari, and an unrecognised reply is treated as a
correction that throws the draft away — so a resident who described a
problem in Nepali and agreed to file it in Nepali lost the complaint.

## A catalogue is not an answer

`find_attractions` and `find_businesses` take no arguments: they return the
whole list and cannot narrow it. Matching the bare word "temple" meant

> *What should I wear to the temples?* → **Places to visit**

A question now gets first refusal from knowledge, and the listing stands in
when nothing answers it.

The first version of that rule was too broad. Handing *every* question to
knowledge first turned "what things to do in Bhaktapur" into **Emergency
Contacts**, which matched on the place name and answered confidently. Asking
for the list is itself a question, so phrases that *are* the browse intent
("things to do", "what to see") go straight to the listing, while a topic
noun that can sit inside a specific question does not.

## A gate that made things worse, and was reverted

"do I need a guide" reduces to one content word once stopwords are removed,
so its coverage is 1.00 against anything containing "guide" — hence a
confident answer about Newari cuisine.

The attempted fix was to discount query words appearing in more than 10% of
the corpus, on the theory that a common word cannot identify a document.
Measured, it did the opposite:

| Question | Before | After the "fix" |
|---|---|---|
| व्यवसाय कर कति हो | high | **low** |
| birth certificate | high | **low** |
| property tax rate | high | **low** |
| do I need a guide | high | high |

In a municipal corpus the important words *are* the frequent ones — "tax",
"certificate", "business" appear everywhere precisely because they matter.
The gate demoted every correct answer and left the wrong one untouched. It
was reverted.

The underlying problem stands: coverage over a one-word query carries no
evidence, and there is no tour-guide content to find. Recorded rather than
patched, because a fix that is not measured is how the gate above got
written.

---

# The index had tripled, and retrieval was paying for it

`index_knowledge_base` appended by default. Running it three times in one
session turned 189 entries into **873 byte-identical chunks**, every title
present three times.

The cost is not storage. `search()` reconsiders its top 8 candidates by
coverage, so three copies of one document occupy three of those slots:

```
building permit fees
  cov=0.33  Visitor Rules & Entry Fees     <- x3
  cov=0.33  Visitor Guidelines             <- x3
  cov=0.33  Getting Around Bhaktapur       <- x2
```

Eight slots, three documents, and the Act that sets building-permit fees
never entered the pool. It had been reaching it at 0.67 an hour earlier.

This also produced a false alarm. Deduplicating the synonym expansions looked
like it had caused the regression, because that was the change in hand when
the symptom appeared. It had not — the third index run had.

The command is the only writer of `KnowledgeChunk`, so the table is entirely
derived and replacing it is always correct. Replacing is now the default,
`--append` is available and documented as almost never wanted.

## Withdrawn content never left the index

Writing the idempotence test surfaced a second bug. With no active entries
the command wrote "KnowledgeBase is empty" and returned **before** deleting
anything, so chunks whose source had been deactivated stayed indexed and
kept being served. A superseded fee schedule would have outlived its own
withdrawal. The index is derived; when the source goes, the chunks go.

## Synonyms have to agree with the stemmer

`SYNONYM_INDEX` was keyed on raw words while documents are matched on stemmed
tokens. "robbed" stems to "robb", so the synonym written as `robbed` was
never once consulted — it could not be. The index is now built after `_stem`
and passes both keys and values through it, and deduplicates: "stay" and
"staying" both stem to "stay", and an expansion listed twice counts twice in
the BM25 sum.

---

# Questions no document can answer

"How many complaints are open" came back as the **lost-passport guide**,
with full confidence. "What is the complaint resolution rate" did the same.
These were the worst answers in the system.

## Two scoring fixes tried, measured, and rejected

The instinct is to treat this as a confidence problem. It is not, and the
numbers say so. Over a dozen known-good and known-bad answers:

| | coverage | margin (top vs 2nd) |
|---|---|---|
| `birth certificate` (right) | 1.00 | **0.02** |
| `complaint resolution rate` (wrong) | 0.33 | **0.20** |
| `व्यवसाय कर कति हो` (right) | 0.67 | 0.05 |
| `do I need a guide` (wrong) | 1.00 | 0.01 |

Neither signal separates them. A correct answer can be a hair ahead of the
runner-up, and a wrong one can win comfortably.

A second attempt — "a *when* question needs a passage containing a time" —
failed the same way. It correctly rejected the garbage-collection answers,
then rejected *when is Bisket Jatra* (the festival page names no clock time)
and accepted *opening hours of Durbar Square* → Emergency Contacts, which
happens to contain the word "hours".

Recorded rather than shipped. The earlier corpus-frequency gate was written
without measuring and demoted every correct answer in the app; these two
were measured first and did not earn their place.

## What did work: ask what kind of thing is being asked for

Caseload questions are not a document question at all. They are caught by
what they ask for — a measure word plus a record noun — and declined:

> I can't report on how many complaints or requests the municipality is
> handling — those figures are not something I have access to, and other
> people's cases are not public.

The reply names where the figures do live (the dashboard for staff, *my
complaints* for one's own, a `BK-` reference for a single case) and leaks no
counts. Both languages.

It is checked after the filing flow, so "garbage is piling up and many
complaints are ignored" is still heard as a report, and it steps aside for
"my complaints", which has a tool behind it. "How many days for a birth
certificate" is untouched: it has a measure word and no record noun.

## Still content gaps, not retrieval gaps

There is **no procedural content** for either of these:

- how to get a water connection (`पानीको धारा कसरी जोड्ने`)
- when household waste is collected (`फोहोर कहिले उठाउँछ`)

The only matches are fee-schedule lines from the आर्थिक ऐन. So a resident
asking when their rubbish is collected is shown *फोहोर फ्याँक्न जरिवाना* —
the littering fine for tourists — or a monthly cleaning charge levied on
NGOs, framed as quoted from municipal records.

No amount of ranking fixes this. The municipality publishes a collection
schedule and a connection procedure; until those are in the corpus, the
honest outcome is the no-answer reply, and the honest fix is the content.

---

# The water-connection procedure was there all along

The previous pass recorded "how to get a water connection" as a content gap.
It was not. The citizen charter documents it, in section 5:

> **ड धारा/विद्ुत जडान सिफारिस** — क_ निवेदन, ख_ जग्गाधनी प्रमाण पूर्जा,
> ग_ चालु आ.ब.को मालपोत तिरेको

The procedure, the documents required, the fee and the responsible officer
are all written down. A resident asks `पानीको धारा कसरी जोड्ने`. Of three
words only `धारा` is shared — the charter never says `पानी`, and `जोड्ने`
is not the string `जडान`. One word of three scores 0.33, below the gate, so
the assistant reported that the municipality had no answer for a service it
publishes a full procedure for.

The expansion map had only ever crossed languages. Nothing connected two
Nepali words for one thing. Adding `धारा`↔`पानी` and `जडान`↔`जोड्ने` takes
the query to 1.00 against the charter, and every tax, permit and
registration query is unchanged — `धारा` also means a legal article, and the
Act still wins those.

**The lesson is about the gap list, not the vocabulary.** "No content" was
asserted from a search that used the citizen's words. The corpus had to be
searched in the *document's* words to tell a real absence from an unreachable
presence.

## Waste collection is a real absence

Searched the same way — `फोहोर`, `सरसफाइ`, `कुहिने`, `संकलन` — and there is
no schedule and no procedure anywhere in the corpus, only fee lines and the
visitor code of conduct. The municipality does not appear to publish a
collection schedule online either.

Correcting the previous entry: the **Nepali** question falls through
honestly (`confidence=low`, no answer given). It is the **English** *when is
garbage collected* that returns the wrong thing — the tourist littering
fine — at `medium`, because `garbage` matches and `collect` does not, and
one word of two is 0.50.

A third scoring idea was tested here: require two matched content words for
`medium`. It would demote *emergency number*, which is a correct answer also
sitting at 0.50 on one matched word. Three heuristics have now been measured
against this corpus — corpus frequency, top-two margin, and absolute matched
terms — and none separates the good answers from the bad. Retrieval scores
are not where this is fixable. The schedule is.

## Re-checking the whole gap list in the document's words

Applying that lesson to every remaining gap found two more services that
were never missing, only unreachable:

| Recorded as | Actually in the charter |
|---|---|
| senior citizen allowance | §27 — `सामाजिक सुरक्षा भत्ता पाउन परिचय पत्र वितरण` |
| disability allowance | §28 — `अपांगता कार्डको फोटोकपी`, severe-disability procedures |

Neither was reachable from English: `भत्ता`, `ज्येष्ठ` and `अपांगता` were
not in the bilingual map. Mapped, both answer in both languages, and every
tax, permit, registration and tourism query is unchanged.

Preeti conversion matters here. The scanned charter renders these as
**ज्येषठ** and **अपांगता**, not the standard `ज्येष्ठ` / `अपाङ्गता`. A term
nobody spells the way the document spells it is a term nobody reaches, so
both spellings are mapped.

### What is genuinely absent

Checked the same way and confirmed missing: waste-collection schedule,
wheelchair and step-free access, ATMs and card payment as a visitor service,
luggage storage, drinking-water safety, and how long to spend in the town.
`शौचालय` appears only as a fee for renting mobile toilets, and `एटिएम` only
as a business registration charge — the fee for operating one, not where a
visitor finds one.

These need content from the municipality. The list is now trustworthy,
which the previous one was not.

---

# The scanned documents had lost their conjuncts

Chasing why `विद्यालय` (school) never matched anything turned up a data
fault underneath the whole Nepali corpus.

A halant followed by a vowel sign is not valid Devanagari — the consonant
that belonged between them was dropped in the Preeti conversion. **80
distinct words, 170 occurrences.**

| Word | In the corpus | Times | Correct spelling present |
|---|---|---|---|
| industry | `उद्ोग` | 33 | **0** |
| school | `विद्ालय` | 10 | **0** |
| electricity | `विद्ुत` | 6 | **0** |
| agreement | `सम्भ्ौता` | 7 | **0** |
| to submit | `बुभ्ाउनु` | 5 | **0** |

Not "mostly misspelled" — the correct spelling appears **zero** times. So
the bilingual map's entry for `विद्यालय` had never once matched, and a
citizen asking about industry registration in correct Nepali could not reach
33 mentions of it.

Two faults, both systematic:

- **A dropped य.** `उद्ोग` → उद्योग, `विद्ालय` → विद्यालय.
- **झ arriving as भ्.** The table maps `E` to `भ्` with nothing to complete
  it, so `सम्भ्ौता` → सम्झौता, `बुभ्ाउनु` → बुझाउनु. `भ्` before a
  *consonant* is ordinary Nepali — अभ्यास — and is left alone.

Fixed in three places, because each one is needed:

1. **The converter** now guarantees valid Devanagari on the way out, so a
   fresh import is clean.
2. **The matcher** applies the same rules, so a document imported before the
   converter was fixed still meets a question spelled correctly. The rules
   live with the converter; retrieval imports them rather than keeping a
   second copy that could drift.
3. **The stored text** was repaired — 163 rows. This one is about reading,
   not matching: an answer quoted as the municipal record should not show
   `विद्ालय` to someone who knows the word. A document that looks
   mistranscribed looks untrustworthy.

Verified on 170/170 occurrences repaired, and on a list of ordinary Nepali
words left byte-identical.

**Not fixed:** other artifacts remain, notably digits standing in for
consonants — `व८ा` for वडा — where the Preeti number row carries letters.
Those need the same treatment and a separate pass.

---

# Digits that were really consonants

The second Preeti fault. The legacy number row carries consonants — `8` is
ड, `6` is ट, `9` is ढ — and the converter lifts figures out before
converting to stop a fee schedule turning into letters. It cannot tell a
consonant-digit from a real one, so it occasionally protects the wrong thing
and hands back a Devanagari numeral wedged inside a word.

`व८ा` is **वडा** — *ward*, one of the most common words in a municipal
document.

Eight distinct words, 14 occurrences, all repaired: `मि६र`→मिटर,
`ब९ी`→बढी, `प्रमा०ा`→प्रमाण (the zero plus long-a was ण), `प्रतिगो६ा`→प्रतिगोटा.

## A second-order bug fell out of it

`प्रतिएि६एम` should be प्रति-एटिएम. The short-i is typed before its
consonant in Preeti and hops right during conversion — but it could not hop
over a *protected figure*, so it was left stranded on the wrong side. Fixed
by restoring the consonants **before** the matra hop.

The hop itself must not be reapplied later: it moves a matra that sits
before a consonant, which is exactly what correct Unicode looks like, so
running it twice turns `मिति` into `मति`. Only the idempotent repairs are
exposed to the matcher and to stored text.

Deciding where a stranded matra belongs needs one distinction: a matra
cannot attach to an independent vowel. `ए` cannot carry one, so in `एि६एम`
it belongs to the hidden consonant. After an ordinary consonant it is
already right — `मि६र` is मिटर, not मटिर, which is what the first attempt
produced.

## Enumerating the edge cases prevented corrupting the corpus

A digit at the edge of a word cannot be judged by position. Listing all 33
candidates and reading them showed **nine were not Nepali at all**:

```
९द्गषति ग्उ ब्च०   = (Square feet)
९ऋषचअगबितषयल०      = (Circulation)
९एबिललषलन०         = (Planning)
```

`९` and `०` are Preeti's brackets, around English that was mangled by being
run through the conversion at all. A positional rule would have "repaired"
those into consonants and made them worse.

So edge digits are **listed, not inferred**, each read in context first. That
recovered `प्रति ३न मिटर` (घन मिटर, the unit a water tariff is charged in),
`९ल जोडाय्` (ढल — the sewer connection charge), `कम्पोष६ विन` (compost bin),
and the verb ending `पर्ने५` → पर्नेछ, which appears throughout the
procedure text.

Content that had been unreachable in **either** language is now reachable in
both: compost bins, sewer connection charges, and water charged by the cubic
metre.

**Still not repaired:** the mangled-English runs themselves. They are
untranslated Preeti, not corrupted Nepali, and they need the conversion not
to have been applied rather than a repair after the fact.
