# Live site QA — pumice-lifting-fervor.ngrok-free.dev

Tested with Chrome DevTools against the live ngrok deployment, as two
personas: a **tourist** (anonymous) and a **resident** (registered account).
Ten rounds, 2026-09-18. Full detail follows the summary.

---

## Read this first — what to fix, in order

### 1. `DEBUG = False`  ·  one line, three problems

Any wrong URL on the public link returns Django's debug 404, which prints
`DEBUG = True`, names `municipal_ai.urls`, and **lists all 59 routes** —
including `django-admin/`, `mayor/`, `chairperson/` and `vendor/`. With a
**configured live Khalti payment key** on the same public tunnel, an
unhandled exception anywhere renders a traceback with local variables.

*I verified access control separately and it holds* — residents get 403s,
anonymous users get login redirects, the public APIs carry no PII. So this
is reconnaissance, not an open door. It is still the cheapest high-value fix
on the list. → *round 4, round 6, round 9*

### 2. The payment path cannot complete a sale

`SITE_URL = http://localhost:8000` while the site runs on the ngrok domain.
Khalti's `return_url` is built from it, so a paying customer is redirected
to **their own machine**; verification never runs and the order is never
marked paid. Separately, checkout decrements stock, deletes the cart and
sends the confirmation **before** payment is attempted — and the failure
path then dumps the customer on the product grid with an empty cart, an
unpaid order, and stock already gone. → *round 9*

### 3. Money figures citizens will act on are wrong

- **Building Permit "NPR 500"** — the Act charges `१.२५`/sq ft + `५००` form
  fee + `रु.१०००` deposit; about **7× more** for a 1,500 sq ft house.
- **Durbar Square "Rs 1500"** — that is the *foreign-national* rate stored as
  if it were the only rate. The correct tiers (SAARC NPR 500) are already in
  the knowledge base; `Attraction.entry_fee` is a single field that flattens
  them. → *rounds 4 and 7*

### 4. Fabricated statistics on the complaint form

`/complaint/` claims **"6 resolved today · 3.2 days avg · 94% satisfaction"**.
The database has 0 resolved, ever, and collects no satisfaction data. These
are hardcoded literals.

**`/transparency/` already computes and displays the honest numbers** (0, 0,
0%, with "—" where a percentage would be meaningless). The correct version
exists on the same site. → *round 1, confirmed round 10*

### 5. Silent failures that look like success

- **Service applications submit with none of the three "required" documents**
  and an invalid phone (`not-a-phone-123` was accepted), then promise
  notification. The application cannot be processed and the office cannot
  make contact. → *round 5*
- **The ward is taken from the applicant's profile, not the property
  address** — I typed a Ward 5 address and it filed under ward 7. → *round 5*
- **Confirmation emails cannot arrive** — `EMAIL_BACKEND` is the console
  backend. → *round 2*

### 6. Two features are entirely non-functional

- **`/map/` renders completely blank.** The CSP at `core/middleware.py:60`
  omits `cdnjs.cloudflare.com`, so Leaflet is blocked and the page dies on
  `L is not defined`. The same gap blocks the map iframe on every attraction
  page — **one fix repairs both**. → *round 8*
- **Every attraction shows "CLOSED"**, including one listed "Open 24 hours".
  `is_open_now()` returns `None` for all of them: the regex at
  `tourism/models.py:44` rejects `AM`/`PM`. → *round 1, root-caused round 7*

### 7. Wrong-season festival dates

**Bisket Jatra listed for 13 July 2027** (it is the April new-year festival,
and Bhaktapur's defining event) and **Indra Jatra for 30 November**
(September). Every event also starts at **3:21 AM** — the seeder inherited
the clock time it ran at. → *round 10*

### 8. Everything was seeded twice

Duplicate marketplace products (**the same shawl at NPR 750 and NPR 650**
from one vendor), duplicate events, and the tripled knowledge index found
earlier are one root cause with three symptoms: non-idempotent seed
commands. → *rounds 9 and 10*

---

## What is working well

Worth stating plainly, because the list above is long:

- **The assistant refuses to invent fees.** Asked the building permit cost,
  it declined and gave the municipal phone numbers. For a government
  assistant this is the single most important behaviour, and it works.
- **Document-age warnings fire correctly**, naming the fiscal year and how
  old it is.
- **Every answer carries a provenance footer** telling the reader to confirm
  fees and dates against municipal records.
- **Authorization holds everywhere tested** — 403s for residents, login
  redirects for anonymous users, no partial pages, no PII in public APIs.
- **The checkout backend is the best code in this audit** — atomic
  transaction, `select_for_update` stock locking, ownership checks, and it
  deliberately rejects unimplemented payment methods rather than silently
  downgrading them.
- **The transparency dashboard is honest**, including publishing its own
  scoring rules.
- **The complaint wizard, the services catalogue and `/services/my/`** are
  well-built and accurate.
- **The CSP is real and really blocks things** — it just was never reconciled
  with the templates.

## Not tested

- **Voting integrity** (double-voting, cross-ward voting) — blocked: no polls
  exist. This is the most important remaining gap.
- The vendor dashboard (needs a vendor account) and the Scan-with-AI upload
  path.

## Test artifacts left in the database

- Service request `SR-202609-XPOJ9L` (marked "QA test application")
- 2 × Singing Bowl in Sita's cart
- Complaint `BK-I7LQN5`
- Account `sita.shrestha.qa@example.com`

No order was placed and no payment details were entered. The Khalti key was
checked as a boolean only; its value was never read.

---

# Round 1 — first pass as tourist and resident

- Started: 2026-09-18, ~08:38 Nepal time
- Account created for testing: `sita.shrestha.qa@example.com` (Ward 7)

## P0 — The complaint form shows fabricated performance statistics

**Where:** `/complaint/` — the page a citizen uses to report a civic issue.

Three figures are displayed as live municipal performance:

| Shown to the citizen | Actual value in the database |
|---|---|
| "**6** complaints resolved today" | **0** resolved today. 0 resolved *ever* |
| "Avg. response **3.2** days" | No complaint has ever been resolved, so there is nothing to average |
| "**94%** satisfaction rate" | No satisfaction data is collected at all |

**They are hardcoded literals**, not computed:

```
templates/complaints/submit.html:806   <span class="fs-num">6</span> complaints resolved today
templates/complaints/submit.html:809   Avg. response <span class="fs-num">3.2</span> days
templates/complaints/submit.html:812   <span class="fs-num">94%</span> satisfaction rate
```

Database state at time of test: **1 complaint total, status PENDING, 0 resolved.**

The homepage contradicts the same page directly — it reports "**0** RESOLVED
THIS MONTH" while `/complaint/` claims six were resolved today.

**Why this is the most serious item here.** The others are bugs. This is a
municipal government telling residents that it resolves complaints in 3.2
days with 94% satisfaction, when it has never resolved one. A citizen
deciding whether this channel is worth using is being given invented
evidence, on an official platform, under the municipality's name. It is also
the exact thing the project's own video brief ruled out ("do not use
fabricated real-world statistics", "no fake city statistics").

**Fix:** compute them, or remove them. If the intent is to show the platform
is new, "0 resolved so far" is honest and costs nothing. A placeholder that
looks like a real statistic is not a placeholder.

---

## P1 — Every attraction in the city shows "CLOSED"

**Where:** every attraction page and card, e.g. `/attractions/nyatapola-temple/`

**What a user sees:** a red `● CLOSED` badge, at 08:38 local time, on a
temple whose own page says it is open `6:00 AM – 8:00 PM daily`. Bhaktapur
Durbar Square (`7:00 AM – 7:00 PM daily`) shows the same. So does
Dattatreya Square, which is listed as **"Open 24 hours"**.

**Why it happens:** `tourism/models.py:44` `is_open_now()` returns `None`
for every single attraction. The regex

```python
r'(\d{1,2}):(\d{2})\s*[-–]\s*(\d{1,2}):(\d{2})'
```

expects `HH:MM – HH:MM`, but the seeded data is `"7:00 AM – 7:00 PM daily"`.
The `AM` sits between the time and the dash, so the match fails and the
method returns `None`. The template treats `None` as false and renders
CLOSED — there is no "hours unknown" state.

Two further defects hide behind the first: the parser **ignores AM/PM**, so
even with a matching format `8:00 PM` would be read as `08:00`; and
`"Open 24 hours"` contains no time pattern at all.

**Verified:** `is_open_now()` returned `None` for all 6 attractions at
08:39 +0545.

**Impact:** a visitor planning a morning at Nyatapola is told the tallest
temple in Nepal is shut. This is the single most damaging bug found.

---

## P1 — Registration states the wrong password rules and discards progress

**Where:** `/register/`, step 2

**What a user sees:** the checklist promises three rules —
*At least 8 characters · One uppercase letter · One number*.
`BhaktapurQA2026` satisfies all three. On submit the server answers:

> Password must be at least 8 characters with 1 uppercase, 1 digit, and
> **1 special character.**

The fourth rule is never shown. Two further problems compound it:

1. The failure throws the user back to **step 1**, not to the password field.
2. The error renders at the top of the form, far from the input that caused
   it — and the step-2 checklist **still lists only three rules** on the
   retry, so a user who did not read the server message carefully will fail
   again.

**Impact:** a sign-up form that rejects a compliant password and then loses
the user's place is a direct conversion loss on the platform's main call to
action ("Join Bhaktapur — Free").

---

## P2 — The unverified phone number is still live on the site

**Where:** `/attractions/bhaktapur-durbar-square/` → Visitor Info → Phone

Shows **`+977-1-6610000`**.

This is the number removed from the codebase and from `KnowledgeBase` /
`KnowledgeChunk` yesterday, because the municipality publishes no such
number (the published lines are `977-01-6613957` and `977-01-6610096`).

**The earlier fix was incomplete:** it corrected the knowledge tables and the
source files but never touched `tourism.Attraction.phone`. One row still
carries it, and it is the city's most-visited landmark page.

**Verified:** `Attraction` 1 row; `Business` 0 rows.

---

## P2 — The city's founding date is given three different ways

| Where | Claim |
|---|---|
| Homepage hero | `EST. 1620 CE` |
| Homepage ticker | `FOUNDED 1620 CE` |
| Register page | `1690 B.S. EST.` |
| Footer, every page | `1,200 years of Newari heritage` |

1690 BS ≈ 1633 CE, so BS and CE are also being mixed. 1,200 years does not
reconcile with either. For a government heritage platform this is the kind
of detail a local reader notices immediately.

---

## P3 — "None" leaks into the UI where a price or rating is missing

**Where:** homepage cards, and business/marketplace listings

- Attractions: `★★★★★ /5 · None` — the rating number is absent and the
  entry fee renders the literal string `None`
- Businesses: `★ None`
- Marketplace: `NPR by` — price and vendor name both empty
- Events: `NPR` with no amount

The detail pages handle this correctly (Nyatapola shows "Free"), so it is the
card templates missing a `|default` filter.

---

## P3 — The embedded map is blocked on attraction pages

`/attractions/nyatapola-temple/` embeds an OpenStreetMap iframe that renders:

> This content is blocked. Contact the site owner to fix the issue.

The "GET DIRECTIONS" link beside it works, so the fallback is fine — but the
visitor sees an error box where a map should be.

---

## Checked and clean so far
- No console errors on the homepage or attraction pages.
- The registration wizard preserves name, email and ward across a failed
  submit (only the step position is lost).

---

# Round 2 — resident journey, end to end

Filed a real complaint as the test resident. It succeeded: reference
**BK-I7LQN5**, stored with the right category, priority, ward, location and
user link. The four-step wizard is genuinely good — the review step is
accurate, and name/email/ward pre-fill from the profile.

Four problems surfaced along the way.

## P1 — The success page promises an email that cannot arrive

The confirmation says, in green:

> ✓ Saved to your account · You'll get an email at
> **sita.shrestha.qa@example.com** when status changes

Neither half of that is currently true:

1. **The email backend is `console.EmailBackend`.** Mail is printed to the
   server's terminal and sent nowhere. On a public deployment no citizen
   will ever receive one.
2. **The address was not even stored.** The POST body carried
   `email=sita.shrestha.qa@example.com` — confirmed in the request — but the
   saved complaint has `email = None`. The form collected it and dropped it.

The complaint is linked to the user account, so a fallback to `user.email`
is possible, but the field the form explicitly asked for was discarded.

**Impact:** a citizen files an issue, is told they will be emailed, and
hears nothing. They have no way to distinguish "no update yet" from "this
never worked".

## P1 — The site is served by Django's development server, with DEBUG on

Response header on every request:

```
server: WSGIServer/0.2 CPython/3.13.12
```

That is `manage.py runserver` — single-threaded, not built for production,
and explicitly warned against by Django for public use. `DEBUG` is also
still `True`.

Together these mean: one slow request blocks every other visitor, and any
unhandled exception renders a full traceback with settings and local
variables to whoever triggered it.

## P2 — The blocked map is a Content-Security-Policy gap

Root cause of the "This content is blocked" box on attraction pages. The CSP
sent with every response is:

```
default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com;
font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob:; connect-src 'self';
frame-ancestors 'none'; base-uri 'self'; form-action 'self';
```

There is **no `frame-src` directive**, so iframes fall back to
`default-src 'self'` and the OpenStreetMap embed is refused. Adding
`frame-src https://www.openstreetmap.org` fixes it.

The same gap will break the "click on the map to pin the location" feature
offered in step 3 of the complaint form — that control is advertised in the
UI but no map element is present in the accessibility tree.

## P2 — Complaint categories are not reachable by keyboard or screen reader

In step 1, the seven category cards (Infrastructure, Sanitation, Water
Supply, Electricity, Road & Transport, Noise & Pollution, Other) appear in
the accessibility tree as plain `StaticText`. They carry no button or radio
role and no accessible name.

A sighted mouse user is fine. A screen-reader user is told there is text on
the page, not that there are seven choices, and cannot tell which is
selected. Keyboard-only users cannot reach them.

For a government service this is the kind of barrier that excludes exactly
the residents least able to visit the ward office in person.

## Positive findings worth keeping

- The security headers are otherwise solid: `frame-ancestors 'none'`,
  `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: same-origin`,
  session cookie `HttpOnly` + `SameSite=Lax`, CSRF token present on the form.
- Ward, name and email pre-fill correctly from the signed-in profile.
- The reference ID is issued immediately and clearly, with a copy button.
- The review step accurately reflects everything entered.

---

# Round 3 — tracking a complaint, and an anonymous-visitor privacy check

## P1 — The tracking form mangles the reference ID it tells you to enter

**Where:** `/complaint/track/`

The field is labelled and placeheld **`Complaint ID (BK-XXXXX)`**, which tells
the user to include the `BK-` prefix. The success page displays the reference
as `BK-I7LQN5` and offers a **Copy ID** button that copies exactly that.

Doing what the page instructs fails:

| Typed | Field becomes | Result |
|---|---|---|
| `BK-I7LQN5` | **`BK-BK-I7L`** | "No complaint found with that ID." |
| `I7LQN5` | `BK-I7LQN5` | Works — redirects to the status page |

The input auto-prepends `BK-` to whatever is typed, then a maxlength clips
the result to 9 characters. So the prefix the placeholder asks for is the
one thing that breaks it.

It also writes the mangled value into a **RECENT** chip (`BK-BK-I7L`), so a
user who clicks their own history repeats the failure.

**Impact:** the documented path — copy the ID from the confirmation, paste it
into the tracker — cannot succeed. This is the whole point of issuing a
reference number.

**Also:** `/complaint/track/?id=BK-I7LQN5` does not prefill the field, so
deep links from email or the success page would not work either.

## P3 — "Verified Citizen Report" is a trust badge with nothing behind it

The status page shows a green **✓ Verified Citizen Report** badge on a
complaint filed two minutes earlier that no official has looked at. If it
only means "submitted while signed in", the word "Verified" overstates it on
a government page, where a reader will take it to mean the municipality
checked the claim.

## P3 — Breadcrumb says "My Complaints" to signed-out visitors

The status page renders `Home / My Complaints / BK-I7LQN5` even for an
anonymous visitor who has no account and no complaints.

## Checked and clean — anonymous access is handled correctly

Looking up someone else's reference as a signed-out stranger returns the
issue but **masks the submitter**: `SUBMITTED BY  S...***`. Title,
description, location, ward and dates are shown; the reporter's identity is
not. Co-signing requires login.

That is the right balance for a civic tracker — the issue is public so
neighbours can support it, the person is not — and it matches the
public-by-reference design in the AI tool layer.

## Deployment note — every first-time visitor meets an ngrok warning

Because the site is served through a free ngrok tunnel, a new visitor sees an
interstitial before the site loads:

> You should only visit this website if you trust whoever sent the link to
> you. **Be careful about disclosing personal or financial information like
> passwords, phone numbers, or credit cards.**

They must click "Visit Site" to continue — and the page they then reach asks
for a name, email, phone and password. For a municipal service this is a
poor first impression and undercuts the trust the platform needs. A custom
domain removes it.

---

# Round 4 — services, fees, and what the public URL gives away

## P0 — Any wrong URL hands an anonymous visitor the site's entire route map

I asked the live site for a page that does not exist:

    GET https://pumice-lifting-fervor.ngrok-free.dev/nonexistent-probe-1323338
    → HTTP 404, 15,459 bytes

That is not a "page not found" page. It is Django's debug 404, and it prints:

- `Using the URLconf defined in municipal_ai.urls`
- `DEBUG = True`
- **all 59 URL patterns in the application**, including:

      django-admin/        admin/          dashboard/
      mayor/               chairperson/    vendor/
      ward/<int:ward_number>/chairperson/  transparency/
      api/map/pins/        ^api/search/suggest/$

Nobody needs to guess where the mayor's panel or the admin login is — a
single bad URL lists them. This is the concrete, demonstrated consequence
of the `DEBUG=True` note recorded earlier in this file, and it is worse
than that note implied: with DEBUG on, any unhandled exception in any view
also returns a full traceback including local variables, which can carry
settings values and query contents.

**Fix:** set `DEBUG=False` before this URL is shared with anyone. That
single change turns all of the above into a blank 404. It is one line.

## P1 — The Services page states fees the municipality's own Act contradicts

`services/views.py:11-47` hardcodes a six-service catalogue with flat fees:

| Service | Site says | What the Act says |
|---|---|---|
| Building Permit | NPR 500 | `१.२५` **per square foot** + `५००` form fee + `रु.१०००` deposit |
| Water Connection | NPR 1500 | no flat figure; recommendation fees only (`१,०००` for industrial) |
| Birth Certificate | NPR 50 | charter shows tiered fees; registration within the legal window is `निःशुल्क` |
| Marriage Registration | NPR 200 | charter shows `रु.१२५।-` for the related certificate line |

Source for the right-hand column: `आर्थिक ऐन (कर तथा शुल्क) 2083/084`
chunks 83, 86, 92 and `नागरिक वडापत्र 2076/077` — both already in this
platform's own knowledge base.

The building permit line is the one that matters most. A citizen reading
"Building Permit — NPR 500" and planning a 1,500 sq ft house would budget
NPR 500. On the Act's schedule that is NPR 500 (form) + ~NPR 1,875
(1.25 × 1,500) + NPR 1,000 (deposit) before any other charge — roughly
**seven times** what the page implies. These numbers carry no source
citation and no fiscal year, so there is no way for a reader to tell they
are estimates.

**Fix:** either cite the fiscal year and source next to each fee, or drop
the figures and link to the Act. Publishing an uncited fee that undercuts
the real one by 7× is the kind of error a municipality gets held to.

## P1 — The same question gets three different answers depending how you ask

Asked as a signed-in resident, on the live site, within one minute:

1. **Services page** → "Building Permit · NPR 500" (confident, no source)
2. **Chat, in English** — *"How much does a building permit cost? I want to
   build a 1500 sq ft house."* → *"I don't have the specific fee details for
   a building permit in Bhaktapur"* + contact details
3. **Chat, in Nepali** — *"नक्सा पास दस्तुर कति लाग्छ?"* → three chunks of the
   2076/077 charter with real fee figures

The assistant's English refusal is *correct behaviour* — it declined to
invent a fee rather than guessing, which is exactly the fail-closed rule.
The problem is the other two.

- **The English path misses content the Nepali path finds.** The fee tables
  are indexed and reachable; "building permit" simply does not expand to
  `नक्सा पास` / `नक्शा पास`. This is a gap in the bilingual term expansion,
  not a gap in the corpus.
- **The Nepali path returns the 7-year-old charter, not the current Act.**
  The `आर्थिक ऐन 2083/084` contains the current per-square-foot schedule and
  was not preferred over the 2076/077 document.

The age warning did fire on the Nepali answer — *"This comes from a 2076/077
document, 7 years older than the municipality's current records"* — so the
safety net works. But a safety net that says "this may be stale" is a poor
substitute for returning the current document that is sitting in the index.

**Fix:** add `building permit / नक्सा पास / नक्शा पास / भवन निर्माण इजाजत` to the
synonym map, and prefer the newest fiscal year when two documents cover the
same fee.

## P2 — Nepali answers are raw document dumps; English answers are written prose

The English question produced a composed reply. The Nepali question produced
three verbatim chunks of scanned charter text, headed *"नागरिक वडापत्र
(2076/077) — 18"*, including the OCR artefacts (`य्जाजत`, `र्वष`, `क्षे.फ`).

A Nepali-speaking resident is the *more* likely user of a Bhaktapur
municipal service, and is getting the less finished experience. Whatever the
cause — a synthesis step that only runs on one path — the asymmetry runs the
wrong way for this audience.

## P2 — The site went down mid-session and nothing noticed

Between round 3 and round 4 the site returned `ERR_NGROK_8012`. Nothing was
listening on port 8000; the Django process had exited. It stayed down until
I restarted it by hand:

    nohup python manage.py runserver 0.0.0.0:8000 > /var/tmp/municipal_server.log 2>&1 &

There is no supervisor, so an exit is permanent until a human notices.
Combined with the dev-server finding already recorded, this means the live
URL's uptime currently depends on someone watching it.

## P2 — There is no health endpoint, so an outage cannot be detected

The log shows `GET /health → 404`, eleven times. Something is polling for a
health check that does not exist, so every probe reports failure whether the
app is healthy or not.

**Fix:** a four-line view returning 200 plus a database `SELECT 1` would make
the outage above detectable by any uptime monitor.

## Tested and working

Worth recording what held up, as well as what broke:

- **`/services/`** renders all six services cleanly, each with processing
  time, fee, and an itemised required-documents list. The information
  architecture is good — the fees are the problem, not the page.
- **The assistant refused to invent a building permit fee.** It offered the
  municipal phone numbers instead. This is the single most important
  behaviour for a government assistant and it is working.
- **The document-age warning fired correctly**, naming both the document's
  fiscal year and how old it is, and advising confirmation with the ward
  office.
- **Every answer carried its provenance footer** — "Written by the assistant
  using city data. Confirm any fee, date or phone number against municipal
  records before relying on it."
- **The verified contact numbers** (`977-01-6613957`, `977-01-6610096`)
  appeared correctly in the fallback response.

## Still untested

Service application submission end-to-end, My Applications, the AI chat as a
tourist, map, itinerary planner, marketplace and cart, notifications, the
transparency page, and the vendor dashboard.

---

# Round 5 — applying for a service, end to end

I applied for a **Water Connection** as the signed-in resident (Sita) and
deliberately submitted a bad application to see what the system would catch.
It caught nothing. Reference issued: `SR-202609-XPOJ9L`.

## P0 — The form accepts an application with none of the "required" documents

The page header says **DOCUMENTS REQUIRED** and lists three:

    Property ownership proof
    Citizenship copy
    Ward recommendation letter

I uploaded none of them and pressed Submit. The application went through and
the site replied:

> ✅ **Application Submitted!**
> Your Water Connection application has been received. You will be notified
> when the status changes.
> **14 days** PROCESSING TIME · **NPR 1500** FEE

The stored row confirms all three are empty:

    document_1 = ''   document_2 = ''   document_3 = ''

So a citizen submits nothing, is told they are in the queue, and starts
counting 14 working days. The application cannot be processed and they will
not find out until someone at the ward office opens it — if anyone does.
This is the worst kind of failure for a government service: it does not look
like a failure to the person affected.

**Fix:** make the three file inputs `required`, or, if partial submission is
intentional, change the success page to say which documents are still
outstanding and that the clock has not started.

## P1 — No phone validation; the only contact channel can be garbage

I entered `not-a-phone-123` in a field labelled **PHONE NUMBER \*** with the
placeholder `+977-98XXXXXXXX`. It was accepted and stored verbatim:

    applicant_phone = 'not-a-phone-123'

Compounding P0: the application is missing all its documents, and the office
has no working number to ask for them. The two defects together produce an
application that can neither be processed nor chased.

**Fix:** validate against Nepali mobile/landline formats server-side. The
placeholder already states the expected shape; nothing enforces it.

## P2 — The ward is taken from the account, not the property address

I typed `Ward 5, Dattatreya Square, Bhaktapur` as the address. The stored
record says:

    ward_number       = 7                                     ← from Sita's profile
    applicant_address = 'Ward 5, Dattatreya Square, Bhaktapur' ← what I typed

The form never asks which ward the property is in; it silently inherits the
ward on the account. A water connection is administered by the ward the
*property* sits in, not the ward the applicant happens to live in. Anyone
applying for a relative, for a second property, or after moving will have
their application routed to the wrong ward office, with no warning to
either party and nothing on screen showing which ward received it.

**Fix:** ask for the property ward explicitly on any property-linked service,
or show the inherited ward on the form so a mismatch is visible.

## P2 — The quoted fee and deadline are display-only and never recorded

The form and success page both show **NPR 1500** and **14 days**. Neither is
stored:

    fee_amount     = ''    ← empty
    estimated_ready = ''   ← empty

The numbers exist only as literals in `SERVICES_CATALOG` and are rendered,
not captured. Consequences:

- there is no record of what the applicant was quoted, so if the catalogue
  is edited later there is no way to honour the original figure;
- `estimated_ready` being empty means no due date exists, so SLA compliance
  cannot be measured and no overdue alert can fire — the "14 days" is a
  promise nothing tracks.

**Fix:** stamp `fee_amount` and `estimated_ready` onto the row at submission
from the catalogue values in force that day.

## P3 — The application form has the same label gap as the complaint form

The accessibility tree shows the inputs with no associated labels:

    textbox required value="Sita Shrestha"      ← no accessible name
    textbox "+977-98XXXXXXXX" required          ← announces the placeholder
    textbox "Your full address" multiline required

The visible captions (`FULL NAME`, `PHONE NUMBER`, `ADDRESS`) are plain text
rather than `<label for=...>`. A screen-reader user hears the placeholder or
nothing at all. This mirrors the complaint form's 19-inputs-vs-7-labels gap
already recorded and suggests a shared template pattern worth fixing once.

## Working well

- **`/services/my/`** lists the application cleanly — icon, reference, service
  name, submission date, status chip, Track link. No `None` leakage, unlike
  the marketplace pages.
- **The reference number format** (`SR-202609-XPOJ9L`) encodes year and month
  and is easy to read back over a phone.
- **The name field was pre-filled** from the profile, which is the right
  default.
- **The success page tells the applicant to save the reference number** and
  offers both "Track My Application" and "Apply for More".

## Note — test data left in the database

This submission is a real row in the live database:
`SR-202609-XPOJ9L`, marked `QA test application - please ignore.` in its
details field. I have not deleted it — say the word and I will.

---

# Round 6 — authorization, tested against the leaked route map

Because the debug 404 hands out every route (P0, round 4), the obvious next
question is whether knowing them buys an attacker anything. I tested each
privileged route twice: once as a signed-in ordinary resident, once as an
anonymous visitor.

| Route | As resident (Sita) | As anonymous |
|---|---|---|
| `/mayor/` | **403 denied** | redirect to login |
| `/chairperson/` | **403 denied** | redirect to login |
| `/dashboard/` | **403 denied** | redirect to login |
| `/vendor/dashboard/` | redirect to login | — |
| `/django-admin/` | redirect to login | — |
| `/services/my/` | 200 (own data) | redirect to login |
| `/api/map/pins/` | 200 | 200 (public data) |
| `/api/search/suggest/` | 200 | 200 (public data) |

**Authorization holds.** An ordinary logged-in resident cannot reach the
mayor, chairperson, staff or vendor areas — the role decorators reject them
with 403 rather than leaking a partial page, and anonymous visitors are sent
to login. The route disclosure is an embarrassment and a reconnaissance aid,
but it is not by itself a privilege escalation. That is worth knowing before
anyone panics about P0 — the fix is still one line, but nothing is currently
standing open.

## The two public APIs were checked for leakage and are clean

`/api/map/pins/` returns 61 pins to anonymous callers — 34 attractions, 27
businesses — with fields:

    type · id · name · lat · lng · category · description · address ·
    entry_fee · url · rating

No complaints, no citizen names, no phone numbers, no email addresses. I
grepped the full payload for `phone`, `email`, `977-9`, `@`, `reporter` and
`submitted_by`: **no matches**. Exposing attractions and businesses to
anonymous users is the intended behaviour for a tourist map, so this is
correct.

One incidental note: the payload carries `"rating": null`, which is the
source of the literal `None` appearing in the UI (recorded as P3 earlier).
Fixing it at the serializer would fix both symptoms.

## Summary of security posture after six rounds

- **Fix now:** `DEBUG=False`. It is the single highest-value change on this
  list and it closes the route disclosure and the traceback exposure at once.
- **Holding correctly:** role-based access control, login redirects, per-user
  data isolation, public API scoping.
- **Still outstanding from earlier rounds:** dev server in production,
  no supervisor, no health endpoint, CSP gap blocking the map.

---

# Round 7 — the tourist experience

Asked as an **anonymous visitor** (no account), which is how nearly every
tourist will arrive:

> *"I'm a tourist arriving tomorrow. What's the entry fee for Durbar Square
> and is it open on Saturday?"*

## P1 — Entry fee is a single number; Bhaktapur charges by nationality

The answer given: **Bhaktapur Durbar Square · 7:00 AM – 7:00 PM daily ·
Rs 1500.00**

The model backing this has exactly one fee field:

    Attraction.entry_fee = 1500.00      # a single DecimalField

Bhaktapur Durbar Square does not have one entry fee. It has a tiered
structure — a foreign-national rate, a lower SAARC rate, and free entry for
Nepali citizens. The schema cannot express that, so whatever single number is
stored is wrong for two of the three groups. A Nepali citizen is told to
expect a Rs 1,500 charge they do not owe; a SAARC visitor budgets several
times the real rate.

**Corrected in round 8:** the platform's own knowledge base *does* carry the
tiered rates — a Visitor Rules chunk states *"Entry fee: NPR 1500 for
foreigners (covers all squares). SAARC nationals: NPR 500."* So `1500.00` is
not an outdated figure; it is the **foreign-national rate stored as if it
were the only rate**. That makes this purely a structural problem, and a
sharper one: the correct tiers are already in the system, and the attraction
listing is flattening them. The chat can answer this correctly from
documents while the attractions page and the "Places to visit" list cannot.

**Fix:** replace `entry_fee` with tiered fields (foreign / SAARC / Nepali) or
a small related table, and cite the source and effective date. For a tourism
platform this is the single most frequently asked question on the site.

## P2 — The assistant lists ten attractions instead of answering the question

The tourist asked two specific things — *the fee for Durbar Square*, and
*whether it is open Saturday*. What came back was a **"Places to visit"**
catalogue of ten attractions, with Durbar Square as the first row.

Both answers are technically present: the row shows `Rs 1500.00` and
`7:00 AM – 7:00 PM daily`, and "daily" does cover Saturday. But the visitor
has to extract them from a list they did not ask for, and the Saturday part
is never addressed in words. A direct reply — *"Rs 1,500 for foreign
nationals; open 7 AM to 7 PM every day, including Saturday"* — is the
answer; the list is a browse result.

This looks like a named-entity question being routed to the browse handler.
Worth checking that a question naming one attraction and asking a specific
attribute is not being classified as "show me attractions".

## P1 confirmed at the data layer — `is_open_now()` returns None for everything

Verified directly against the database. **Every** attraction returns `None`:

    Bhaktapur Durbar Square   '7:00 AM – 7:00 PM daily'   → None
    Dattatreya Square         'Open 24 hours'             → None
    Nyatapola Temple          '6:00 AM – 8:00 PM daily'   → None
    Bhairavnath Temple        '6:00 AM - 9:00 PM'         → None

This confirms the "every attraction shows CLOSED" finding from round 1 and
pins down the cause. `tourism/models.py:44` parses with:

    re.match(r'(\d{1,2}):(\d{2})\s*[-–]\s*(\d{1,2}):(\d{2})', self.opening_hours)

The stored strings carry `AM`/`PM` (`7:00 AM – 7:00 PM daily`), which the
pattern does not allow, so it never matches. Note it fails even for
`Open 24 hours`, which has no times at all and should simply return True.

The revealing part: the **chat answer displays the hours correctly** because
it renders the raw string, while the attraction page shows CLOSED because it
calls `is_open_now()`. Same data, two code paths, one broken — which is why
this looked like a display bug in round 1 and is actually a parser bug.

**Fix:** parse 12-hour times with meridiem, special-case "Open 24 hours", and
return `None` only when the string genuinely cannot be understood — then
render unknown hours as "Hours unavailable" rather than "CLOSED". Telling a
tourist a temple is closed when it is open is the costlier error.

## Working well for tourists

- The attraction list is **rich and accurate on hours** — ten attractions
  with per-site opening times and fees, correctly marking free sites free.
- **No account needed.** The assistant answered anonymously with no login
  wall, which is right for a visitor who will use the site once.
- Free-entry sites are labelled **"Free entry"** rather than "Rs 0", which
  reads properly.

---

# Round 8 — map, trip planner, and what the CSP is actually breaking

## P1 — The City Map is completely blank, and the cause is the CSP

`/map/` is a primary navigation item. It renders every piece of furniture —
Explore/Directions tabs, a "Search Bhaktapur…" box, category filters
(All · Sites · Food · Hotels · Shops · Events), zoom controls, a locate
button — around **an empty cream rectangle**. No basemap, no markers, no
city. The results list beside it is empty too.

The data is fine: `/api/map/pins/` returns **61 pins** with valid
coordinates. Nothing renders them. The console says why:

    [error] Loading the script 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js'
            violates the following Content Security Policy directive: "script-src 'self' 'unsafe-inline'"
    [error] Loading the stylesheet '…/leaflet.min.css' violates … "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com"
    [error] Loading the script '…/leaflet.markercluster.min.js' violates … "script-src 'self' 'unsafe-inline'"
    [error] Uncaught ReferenceError: L is not defined

Leaflet and MarkerCluster are loaded from `cdnjs.cloudflare.com`, which is
not in the policy, so both the library and its CSS are blocked and the map
script dies on `L is not defined`.

**The policy is at [core/middleware.py:60](core/middleware.py#L60)**, and its own comment
says it "allows same-origin scripts/styles and specific external CDNs used by
the templates" — but `cdnjs.cloudflare.com` was never added:

    script-src 'self' 'unsafe-inline';
    style-src  'self' 'unsafe-inline' https://fonts.googleapis.com;
    img-src    'self' data: blob:;
    default-src 'self';          ← also governs frame-src

**This is the same root cause as the "embedded map is blocked" finding from
round 1.** One misconfiguration breaks two features: the whole `/map/` page,
and the OpenStreetMap iframe on every attraction page (blocked by
`default-src 'self'` standing in for `frame-src`). That earlier item was
filed as P3 on the assumption it was cosmetic; it is not, and this raises it.

**Fix** — four additions to `_CSP`:

    script-src  … https://cdnjs.cloudflare.com
    style-src   … https://cdnjs.cloudflare.com
    img-src     … https://*.tile.openstreetmap.org     (basemap tiles)
    frame-src   https://www.openstreetmap.org          (attraction-page embed)

Worth noting the CSP is otherwise doing its job correctly — it is a real
policy that really blocks things, which is better than most deployments. It
simply has not been reconciled with the templates.

## P2 — "Plan Trip" is advertised to tourists and then demands an account

I probed every navigation destination as an anonymous visitor. Exactly one
browse feature is behind a login wall:

    LOGIN WALL  /itineraries/        ← "Plan Trip", in the top nav and footer
    open        /map/ /attractions/ /events/ /businesses/ /marketplace/
    open        /news/ /chat/ /complaint/ /complaint/track/ /transparency/
    open        /services/ /services/notices/
    LOGIN WALL  /marketplace/cart/ /notifications/ /orders/ /vendor/dashboard/

Cart, orders, notifications and the vendor dashboard being gated is correct.
`/itineraries/` is different: it is the **most tourist-facing feature on the
site**, promoted in the primary navigation to signed-out visitors, and it is
the only one that stops them. A visitor in Bhaktapur for a day will not
create an account to see a suggested route — they will leave.

**Fix:** let anonymous visitors generate and view an itinerary; require the
account only to *save* one. That is the pattern the rest of the site already
follows.

## P2 — The "Plan my trip (2 days)" suggestion chip does not plan a trip

The chat's own starter chips include **📅 Plan my trip (2 days)**. Sending
exactly that phrase as an anonymous tourist returns:

- a block of **emergency contact numbers** (police 100, fire 101, ambulance
  102, tourist police 1144, Bhaktapur Hospital), in English and Nepali
- a **Visitor Rules & Entry Fees** block (dress code, photography, guides)

No itinerary. No day 1 / day 2. No suggested order of sites, no timings.

The content returned is accurate and well-sourced — it is simply not an
answer to the question the product itself offered to answer. A promoted
one-click action that returns something unrelated is worse than not offering
it, because the user reads it as the assistant's best effort.

**Fix:** either route this intent to a real itinerary builder, or change the
chip to describe what it actually returns.

## Good news buried in that answer — the tiered entry fee already exists

The same response contained:

> **Visitor Rules & Entry Fees** — Entry fee: NPR 1500 for foreigners
> (covers all squares). **SAARC nationals: NPR 500.** Dress code… Guides
> available at Durbar Square gate (NPR 500–1000/half-day).

So the tiered structure flagged in round 7 is **already documented in the
knowledge base**. The fix there is smaller than it first appeared: the
correct rates exist, and the `Attraction.entry_fee` field is flattening
them. (Round 7 has been corrected accordingly.)

---

# Round 9 — the marketplace, the cart, and a live payment gateway

I did **not** place an order or enter any payment details on the live site.
Everything below comes from reading the checkout code and from configuration
state checked as booleans only — no secret values were read or printed.

## P0 — Khalti's return URL points at `localhost`, so a real payment can never be verified

`SITE_URL` is set to **`http://localhost:8000`** while the site is served at
`https://pumice-lifting-fervor.ngrok-free.dev`. The Khalti callback is built
from it ([marketplace/views.py:319](marketplace/views.py#L319)):

    'return_url': f'{site_url}/marketplace/khalti/verify/'
                   → http://localhost:8000/marketplace/khalti/verify/

A customer who pays with Khalti is redirected, after paying, to
`localhost:8000` — *their own machine*. The verification callback never
reaches the server. So:

- the money leaves the customer's wallet,
- `/marketplace/khalti/verify/` never runs,
- the order stays `payment_status != 'paid'` forever,
- and the customer lands on a connection-refused page.

**`KHALTI_SECRET_KEY` is configured** (verified as a boolean — the value was
not read), so this is not a dormant stub. The gateway is live.

**Fix:** set `SITE_URL` to the public origin. This is one environment
variable and it stands between the platform and taking money it cannot
reconcile.

## P0 — Stock, cart and confirmation all commit *before* payment is attempted

In `checkout_view` the atomic block does all of this **before** the customer
has paid ([marketplace/views.py:262-283](marketplace/views.py#L262-L283)):

    order = Order.objects.create(..., status='pending')
    Product.objects.filter(pk=...).update(stock=F('stock') - item.quantity)   # stock gone
    cart.items.all().delete()                                                 # cart emptied
    _send_order_confirmation(order, fresh_items)                              # "confirmed"
    ...
    if payment_method == 'khalti':
        return redirect(f'/marketplace/khalti/initiate/{order.pk}/')          # payment starts here

If the customer abandons the Khalti page, or the gateway errors, or the key
is missing, the damage is already done: stock decremented, cart destroyed,
confirmation issued, nothing paid.

The failure path makes it worse. `khalti_initiate` bails with *"Payment
gateway not configured. Please use Cash on Delivery"* and redirects to
`marketplace:checkout` — but the cart was just emptied, and `checkout_view`
opens with:

    if not items:
        return redirect('marketplace:list')

So the customer is told to retry with Cash on Delivery and is instead
silently dumped on the product grid, with an empty cart, an unpaid "pending"
order, and stock already deducted. They have no way to complete the purchase
and no indication anything went wrong.

**Fix:** decrement stock and clear the cart on *verified payment*, not on
order creation. For Khalti, reserve stock and finalise in the verify
callback.

## P1 — Checkout offers two payment methods the server always rejects

The checkout form presents four options as equal, selectable radios:

    💵 Cash on Delivery    📱 eSewa    💜 Khalti Digital Wallet    🏦 Bank Transfer

The server accepts only two ([marketplace/views.py:248](marketplace/views.py#L248)):

    if payment_method not in ('cod', 'khalti'):
        ... 'not yet available. Please use Cash on Delivery or Khalti.'

Rejecting rather than silently downgrading is the **right** call, and the
code comment says so explicitly. The problem is purely presentational: a
customer selects eSewa, fills in seven required delivery fields, presses
PLACE ORDER, and only then learns the method does not exist.

**Fix:** disable the two unimplemented radios and label them "coming soon".

## P1 — The cart says "Under Construction" but checkout is fully live

The cart page shows a **COMING SOON — Cart Under Construction** panel:

> Our checkout system is being finalized. You'll be able to purchase local
> Bhaktapur products and pay via Khalti or Cash on Delivery very soon.

Directly beneath it sits **"View Cart Anyway"**, and the cart below that has
a working **PROCEED TO CHECKOUT →** link to a checkout that creates real
orders, decrements real stock, and initiates real Khalti payments — under
the reassurance **"🔒 Secured by Bhaktapur Municipal Platform"**.

Either the warning is wrong or the checkout should be closed. Right now a
customer is told the feature is not ready and is then allowed to spend money
on it.

## P1 — A live payment key is exposed on a DEBUG=True public tunnel

This compounds round 4's P0. With `DEBUG=True`, any unhandled exception
renders Django's technical 500 page, which prints local variables from every
frame. The Khalti code path builds a `payload` and calls the gateway with
`requests`; an exception anywhere in that path can surface request context
on a publicly reachable URL. A configured payment secret plus DEBUG on a
public tunnel is a materially worse combination than either alone.

**`DEBUG=False` is now the single most urgent item in this document.**

## P2 — The same products are listed twice at different prices

13 products, all from one vendor (Bhaktapur Heritage Store), include four
near-duplicate pairs:

| Product | Listed at | And also at |
|---|---|---|
| Dhaka Fabric Shawl | NPR 750 | **NPR 650** |
| Bronze Ganesh Statue | NPR 2200 *(15 cm)* | **NPR 1800** |
| Bhaktapur Pottery Bowl | NPR 850 *(Set)* | **NPR 450** |
| Hand-painted Thangka | NPR 3500 *(Medium)* | NPR 3500 |

The two Dhaka Fabric Shawls have **identical names and different prices**
from the same seller. This looks like the seed command having run twice with
slightly evolved names — the same double-seeding pattern seen earlier in the
knowledge index.

**Fix:** de-duplicate, and add a uniqueness constraint on (vendor, name).

## Working well

The checkout backend is the best-written code found in this audit:

- **`transaction.atomic()` with `select_for_update()`** locks the rows for the
  stock check and decrement — correct concurrency handling, not a read-then-write
  race.
- **Out-of-stock is checked against freshly locked rows** and re-renders with
  accurate subtotals rather than failing blindly.
- **Unimplemented payment methods are rejected, not silently downgraded** —
  with a comment explaining the choice.
- **`khalti_initiate` guards properly**: it verifies ownership via
  `get_object_or_404(Order, pk=order_id, user=request.user)`, refuses
  already-paid orders, and degrades with a message when unconfigured.
- **Cart arithmetic is correct**: 1800 × 2 = 3600, + 100 delivery = 3700, and
  the nav badge updated to 2.

The defects above are ordering and configuration problems around genuinely
careful code.

---

# Round 10 — events, civic participation, transparency

## P1 — Bhaktapur's two most famous festivals are listed in the wrong season

| Event | Site says | When it actually happens |
|---|---|---|
| **Bisket Jatra 2082** | **13 July 2027** | **Mid-April** — it *is* the Nepali New Year festival (Baisakh 1) |
| **Indra Jatra Celebration** | **30 November 2026** | **September** (Bhadra–Ashwin) |

Bisket Jatra is Bhaktapur's defining festival — the chariot procession that
marks the new year, and the single biggest reason a visitor times a trip to
this city specifically. It never falls in July. Indra Jatra never falls in
November.

A tourist planning around these dates books the wrong month. On a platform
published under the municipality's name, for the festival that city is most
known for, this is the kind of error a local spots instantly.

Note the listing also contains a *correct* Bisket Jatra entry
(13 April 2026), so the two contradict each other.

**Fix:** set festival dates from the Nepali calendar, and treat any
festival date as needing a source before publication.

## P1 — Every event in the city starts at 3:21 AM

All 9 events display start times of **3:21 or 3:22 AM** — a Heritage
Photography Walk, a Thangka Painting Workshop, a Newari Food Festival.

The cause is visible by comparing the columns:

    name                              start_date (local)     created_at (local)
    Bhaktapur Heritage Photography…   2026-09-21 03:22:44    2026-09-16 03:23:03
    Thangka Painting Workshop         2026-09-23 03:21:37    2026-09-16 03:21:37
    Newari Food Festival              2026-09-30 03:21:37    2026-09-16 03:21:37
    Indra Jatra Celebration           2026-11-30 03:22:44    2026-09-16 03:22:53

The seeder used `timezone.now() + timedelta(days=N)`, so every event
**inherited the time of day at which the seed script ran** (03:21:37 and
03:22:44) and nobody set a real start time.

This is *not* a timezone bug — `TIME_ZONE = Asia/Kathmandu` and `USE_TZ =
True` are both configured correctly, and the times render properly in local
time. The stored data is simply wrong.

**Fix:** give each event a real start time. Until then, showing the date
without a time would be more honest than "3:21 AM".

## P2 — Events and products were both seeded twice

The two seed timestamps above (`03:21:37` and `03:22:44`) correspond to two
runs, each producing a parallel set:

| Event | Run 1 | Run 2 |
|---|---|---|
| Thangka Painting Workshop | Sep 23 | Sep 26 |
| Newari Food Festival | Sep 30 | Oct 6 |
| Bisket Jatra | Apr 13 2026 | "2082" — Jul 13 2027 |

A visitor browsing sees the same workshop advertised twice on different
dates at the same venue. This is the **same double-seeding** that produced
the duplicate marketplace products in round 9 and the tripled knowledge
index found earlier — one root cause, three visible symptoms.

**Fix:** make the seed commands idempotent (`get_or_create` on a natural
key), and clean the existing duplicates.

## P2 — The Civic section is empty, and its landing page 404s

"Civic" is a dropdown in the primary navigation. Behind it:

    404  /civic/              ← the section root does not exist
    200  /civic/polls/        "No active polls right now."
    200  /civic/proposals/
    200  /civic/petitions/
    200  /civic/meetings/

The sub-pages render correctly with proper empty states — the polls page
says *"Vote on decisions that affect your ward and city. · No active polls
right now."*, which is honest and well-phrased. But the section is entirely
unpopulated, and `/civic/` itself returns the debug 404 (see round 4 P0),
so anyone who reaches the section root gets a page listing all 59 routes.

I could not test voting integrity — whether a resident can vote twice, or
vote in another ward's poll — because there is nothing to vote on. **This
remains the most important untested area**: an unauthenticated or repeatable
vote on a municipal poll would be a serious finding, and it cannot be
assessed until a poll exists.

## The transparency dashboard is honest — which condemns the complaint page

`/transparency/` reports, correctly and without decoration:

    2   Total Complaints Filed
    0   Resolved
    0%  Resolution Rate
    0   Avg. Days to Resolve

    SLA Compliance — CRITICAL 1d · HIGH 3d · MEDIUM 7d · LOW 14d
    (all rows: 0 resolved, 0 within SLA, compliance "—", overdue "None")

This is exactly right: real numbers, computed from real data, with an
explicit "—" where a percentage would be meaningless rather than a
fabricated 0% or 100%.

**It also settles the round 1 P0.** The complaint form claims *"6 complaints
resolved today · Avg. response 3.2 days · 94% satisfaction rate"* while this
page — on the same site, from the same database — says 0, 0 and 0. The
honest computation already exists and is already rendered. There is no
technical reason for the hardcoded figures on `/complaint/` to remain.

The "Civic Champions" leaderboard is also well-judged: it publishes its
scoring rule openly (*10 pts per complaint filed · 50 pts when resolved ·
2 pts per vote cast*) rather than presenting an opaque score.

## Also working

- **`/notifications/`** renders a clean empty state: *"No notifications yet.
  You'll be notified when your complaint status changes."*
- **`/news/`** is populated with real, plausible items (Durbar Square
  Restoration Phase 2, new Visitor Center) and working category filters.
- **The AI Camera Scanner** degrades correctly when no camera is present:
  *"Camera unavailable. Upload a photo to identify it."* with a file-picker
  fallback, and a defined error state.
