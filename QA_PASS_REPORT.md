# QA Pass Report

| | |
|---|---|
| **Generated** | 2026-09-16 19:15 +0545 (three consecutive full runs; numbers below are from the last) |
| **Commit** | `64f41e7` (working tree had uncommitted QA changes, listed below) |
| **Target** | `http://127.0.0.1:8000` (local `manage.py runserver`, `DEBUG=True`) |
| **Produced by** | `./run_tests.sh` — all four layers, not a hand-written summary |
| **Raw logs** | `log/test_report.md`, `log/django_tests.log`, `log/api_smoke.log`, `log/ui_tests.log`, `log/kb_gap_check.log` |

The previous version of this file had no date, no commit, and listed `adminpanel`
three times. It also reported `events`, `news`, `complaints`, `reviews`,
`favorites` and `marketplace` as failing on database errors; those suites were
re-run and all of them pass. Nothing in that report was reproducible, so it has
been replaced with output from an actual run rather than corrected in place.

## Result

```
RUN_SUMMARY: new_failures=0 new_kb_gaps=0 layers_ok=4/4
```

| Layer | Result | Detail |
|---|---|---|
| 1. Django tests | **PASS** | 403 tests, 0 failures, 284s |
| 2. API smoke | **PASS** | 46 passed, 4 skipped (2 write-gated, 2 production-hardening-gated) |
| 3. UI flows (Playwright) | **PASS** | 8 passed, 1 write-gated |
| 4. Knowledge-base gaps | **RAN** | 12 questions asked, 0 unchecked, 2-4 gaps depending on the run (see finding 3) |

Skips are deliberate and named, not silent. The write-gated tests submit real
complaints and the endpoint allows 3 per hour per IP; they are opt-in via
`RUN_WRITE_TESTS=1` and were each verified passing separately. The
hardening-gated tests assert DEBUG leakage is off, which is only meaningful
against a public URL (`EXPECT_PROD_HARDENING=1`).

## What was fixed in this pass

| Problem | Fix |
|---|---|
| Playwright could not launch a browser, so the UI layer never ran | The real cause was disk, not a missing install: `/tmp` is its own 437M partition with 62M free and the download needs 187M. Installed with `TMPDIR=/var/tmp`, and removed the stale chromium-1228 build that no longer matched Playwright 1.63 |
| UI tests navigated to `/complaints/new` → 404 | Route is `/complaint/`. Also `/businesses` 301s; `/businesses/` is correct |
| UI tests drove the complaint form with `getByLabel()` | It is a 4-step wizard whose visible inputs are unlabelled and whose POST values live in mirrored hidden inputs. Rewritten against the real DOM |
| No `playwright.config.ts` existed at all | Added, with `workers: 1` (the app is single-process and the chat endpoints are rate-limited per IP, so parallel workers manufacture 429s) |
| An unreachable app failed all 9 UI tests, reading like app bugs | `tests/ui/global-setup.ts` aborts once with an INFRASTRUCTURE message, matching what `tests/api/conftest.py` already did |
| `run_test_loop.sh` never saw a `RUN_SUMMARY` line, so every run scored "not clean" regardless of results | `run_tests.sh` now emits it, and diffs against `log/known_failures.txt` so "new" means new. Verified by running the loop's own parser against the real report |
| Layer 4 of the loop's 4-layer contract did not exist | Added `scripts/kb_gap_check.py` |
| `pyotp` missing from `requirements.txt` | See below — a production bug, not a test bug |
| Stale `test_smoke.py.bak` / `.placeholder-orig` copies of the old broken suite | Deleted |
| CI called `pytest tests/api/test_smoke.py` and `npx playwright test tests/ui/` directly | `.github/workflows/qa.yml` now calls `./run_tests.sh`, so CI and a developer's terminal cannot drift |

### `pyotp` was missing from requirements.txt

`accounts/views.py` imports `pyotp` inside the two-factor views, so it is
production code, not a test dependency. It was absent from `requirements.txt`,
which means **a fresh deploy would 500 on any 2FA request** — enrolment,
verification and login. The import sits inside the function bodies, so nothing
fails at startup; it only breaks when a citizen turns on two-factor auth.

Added as `pyotp==2.10.0`. `accounts.tests.TwoFactorSecurityTests` now passes;
it was the single error in the 403-test suite.

## Do the tests actually catch anything?

A suite that passes proves nothing on its own, so three defects were injected
and the suite was re-run against each. All three were caught, and all three were
reverted (`git status` on `templates/` is clean):

| Injected defect | Caught by |
|---|---|
| Wizard step-1 validation always returns true (advance with no category) | `blocks step 1 until a category is chosen` |
| Chat error message replaced with a blank panel | `shows an error message, not a blank panel, when the API fails` |
| Business cards stop rendering (simulates the Sep 15 data loss) | `lists businesses` |

The knowledge-base classifier was checked the same way, against eight cases —
empty, too short, deflection-with-only-a-phone-number, the app's own no-answer
fallback, an off-topic answer, and three answers that must **not** be flagged
including a correct Nepali answer to an English question.

## Open findings — not fixed, reported

These are application behaviour, not test defects. None were changed, because
each is a substantive product decision rather than a QA fix.

**1. Retrieval returns confidently off-topic answers.** Two of twelve citizen
questions got a fluent, authoritative-looking answer about something else:

- *"How do I register a new business in Bhaktapur municipality?"* → a list of
  emergency phone numbers.
- *"How much is property tax in Bhaktapur and how do I pay it?"* → a paragraph
  of general geography, prefixed **"Based on our municipal records:"**.

For a government service this is worse than "I don't know": the citizen has no
way to tell a wrong answer from a right one, and the framing asserts it came
from municipal records. Drafts are in `log/kb_drafts/`.

**2. The knowledge base has no material on some common services.** The social
security allowance question returned the app's honest no-answer fallback. That
is correct behaviour and a data gap, not a bug.

**3. Answers are not stable between runs.** The same question answered well on
one run and fell back on the next — `track-complaint` and `social-security` both
did this. Consequence for the loop: `log/known_kb_gaps.txt` accumulates rather
than being replaced, so a gap that merely fails to reappear is not mistaken for
one that was filled.

**4. Complaint submission takes about 20 seconds.** `submit_complaint()` sends
the confirmation email synchronously, then calls
`categorize_complaint_async.delay()`, which blocks on broker retries whenever
Celery is down. Measured at 24.6s end-to-end in the browser. The citizen watches
a spinner the whole time.

**5. The business directory serves a 10-minute cached response.** Anonymous,
unfiltered, first-page requests are cached in `businesses_list`. With Redis down
this is `LocMemCache`, which is per-process — so a fix or a data change can take
up to 10 minutes to appear, and cannot be cleared from outside the process. This
was found because it silently invalidated a mutation test.

## Running it

```bash
python manage.py runserver 127.0.0.1:8000        # layers 2-4 need the app up
MUNICIPAL_AI_BASE_URL=http://127.0.0.1:8000 ./run_tests.sh
```

Opt-in groups, both of which spend a real per-IP quota:

```bash
RUN_WRITE_TESTS=1        # submits real complaints (3/hour per IP)
EXPECT_PROD_HARDENING=1  # assert DEBUG leakage is off; for public URLs only
```
