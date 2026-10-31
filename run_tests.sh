#!/usr/bin/env bash
# Full QA pass: Django tests -> API smoke -> Playwright UI -> knowledge-base gaps.
#
# Ends with the one machine-readable line run_test_loop.sh parses:
#   RUN_SUMMARY: new_failures=<n> new_kb_gaps=<n> layers_ok=<n>/4
#
# Two rules this script exists to keep honest:
#   * "new" means new. Failures and gaps are diffed against the last run's
#     baseline (log/known_failures.txt, log/known_kb_gaps.txt) so a standing
#     problem is not re-reported forever and a fresh one cannot hide in the pile.
#   * A layer that could not run is NOT ok. Missing pytest, a browser that will
#     not launch or a server that is down all leave layers_ok short, because a
#     loop that treats "did not run" as "passed" will report success on an app
#     nobody tested.
set -uo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

REPORT="log/test_report.md"
BASELINE="log/known_failures.txt"
KB_BASELINE="log/known_kb_gaps.txt"
CURRENT="log/.current_failures.txt"

mkdir -p log log/kb_drafts
touch "$BASELINE" "$KB_BASELINE"
: > "$CURRENT"

BASE_URL="${MUNICIPAL_AI_BASE_URL:-http://localhost:8000}"
if [[ -z "${PYTHON:-}" ]]; then
  if   [[ -x .venv/bin/python ]]; then PYTHON=.venv/bin/python
  elif [[ -x venv/bin/python  ]]; then PYTHON=venv/bin/python
  else PYTHON=python3
  fi
fi

TS="$(date '+%Y-%m-%d %H:%M')"
COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo 'no-git')"
layers_ok=0

{
  echo ""
  echo "## Run: $TS (commit $COMMIT, target $BASE_URL)"
} >> "$REPORT"

note() { echo "$1" >> "$REPORT"; }

# ── Layer 1: Django tests ────────────────────────────────────────────────
echo "--- Layer 1: Django tests ---"
if "$PYTHON" manage.py test > log/django_tests.log 2>&1; then
  note "- Layer 1 Django tests: PASS"
  layers_ok=$((layers_ok + 1))
else
  # Django prints "FAIL: test_name (dotted.Path)" / "ERROR: ..." per failure.
  grep -E '^(FAIL|ERROR): ' log/django_tests.log \
    | sed -E 's/^(FAIL|ERROR): /django:/; s/ \(.*//' >> "$CURRENT"
  n=$(grep -cE '^(FAIL|ERROR): ' log/django_tests.log || true)
  if [[ "$n" -eq 0 ]]; then
    note "- Layer 1 Django tests: DID NOT RUN (see log/django_tests.log)"
    echo "django:layer-did-not-run" >> "$CURRENT"
  else
    note "- Layer 1 Django tests: FAIL ($n failing, see log/django_tests.log)"
  fi
fi

# ── Layer 2: API smoke tests ─────────────────────────────────────────────
echo "--- Layer 2: API smoke tests ---"
if ! "$PYTHON" -m pytest --version >/dev/null 2>&1; then
  note "- Layer 2 API smoke tests: DID NOT RUN (pytest not installed for $PYTHON)"
  echo "api:layer-did-not-run" >> "$CURRENT"
else
  MUNICIPAL_AI_BASE_URL="$BASE_URL" "$PYTHON" -m pytest tests/api/ -v \
    > log/api_smoke.log 2>&1
  rc=$?
  if [[ $rc -eq 0 ]]; then
    note "- Layer 2 API smoke tests: PASS"
    layers_ok=$((layers_ok + 1))
  elif [[ $rc -eq 3 ]]; then
    # conftest aborts with 3 when the app is unreachable — infrastructure.
    note "- Layer 2 API smoke tests: DID NOT RUN (app unreachable at $BASE_URL)"
    echo "api:layer-did-not-run" >> "$CURRENT"
  else
    grep -E '^FAILED ' log/api_smoke.log | awk '{print "api:" $2}' >> "$CURRENT"
    n=$(grep -cE '^FAILED ' log/api_smoke.log || true)
    note "- Layer 2 API smoke tests: FAIL ($n failing, see log/api_smoke.log)"
  fi
fi

# ── Layer 3: Playwright UI flows ─────────────────────────────────────────
echo "--- Layer 3: Playwright UI flows ---"
if ! command -v npx >/dev/null; then
  note "- Layer 3 UI flows: DID NOT RUN (npx not installed)"
  echo "ui:layer-did-not-run" >> "$CURRENT"
else
  # Drop the previous run's report first. If npx dies before writing a new one,
  # a stale file would be parsed as this run's failures.
  rm -f log/ui_results.json
  MUNICIPAL_AI_BASE_URL="$BASE_URL" npx playwright test > log/ui_tests.log 2>&1
  rc=$?
  if [[ $rc -eq 0 ]]; then
    note "- Layer 3 UI flows: PASS"
    layers_ok=$((layers_ok + 1))
  else
    # Titles come from the JSON reporter; the text log is for humans.
    "$PYTHON" - <<'PY' >> "$CURRENT"
import json, os, sys
path = "log/ui_results.json"
if not os.path.exists(path):
    print("ui:layer-did-not-run"); sys.exit()
try:
    data = json.load(open(path, encoding="utf-8"))
except Exception:
    print("ui:layer-did-not-run"); sys.exit()

def walk(suite, trail):
    here = trail + [suite.get("title", "")]
    for spec in suite.get("specs", []):
        if not spec.get("ok", True):
            name = " > ".join(t for t in here + [spec.get("title", "")] if t)
            print(f"ui:{name}")
    for child in suite.get("suites", []):
        walk(child, here)

for s in data.get("suites", []):
    walk(s, [])
PY
    if grep -q '^ui:layer-did-not-run$' "$CURRENT"; then
      note "- Layer 3 UI flows: DID NOT RUN (no results written — see log/ui_tests.log)"
    else
      n=$(grep -c '^ui:' "$CURRENT" || true)
      note "- Layer 3 UI flows: FAIL ($n failing, see log/ui_tests.log, screenshots in test-results/)"
    fi
  fi
fi

# ── Layer 4: knowledge-base gap check ────────────────────────────────────
# A gap is a data problem, not a test failure, so it is counted separately and
# never rolled into new_failures.
echo "--- Layer 4: knowledge-base gap check ---"
MUNICIPAL_AI_BASE_URL="$BASE_URL" "$PYTHON" scripts/kb_gap_check.py \
  > log/kb_gap_check.log 2>&1
kb_rc=$?
if [[ $kb_rc -eq 0 ]]; then
  gaps=$(grep -c . log/kb_gaps.txt 2>/dev/null); gaps=${gaps:-0}
  if [[ "$gaps" -eq 0 ]]; then
    note "- Layer 4 knowledge-base gaps: PASS (no gaps)"
  else
    note "- Layer 4 knowledge-base gaps: $gaps gap(s), drafts in log/kb_drafts/"
  fi
  # This layer "ran ok" when it completed its whole sweep. Gaps are reported
  # through new_kb_gaps, which the loop weighs separately.
  layers_ok=$((layers_ok + 1))
elif [[ $kb_rc -eq 4 ]]; then
  note "- Layer 4 knowledge-base gaps: PARTIAL (some questions unchecked, see log/kb_gap_check.log)"
else
  note "- Layer 4 knowledge-base gaps: DID NOT RUN (see log/kb_gap_check.log)"
  : > log/kb_gaps.txt
fi

# ── Diff against the last run ────────────────────────────────────────────
sort -u -o "$CURRENT" "$CURRENT"
touch log/kb_gaps.txt
sort -u -o log/kb_gaps.txt log/kb_gaps.txt

new_failures=$(comm -23 "$CURRENT" <(sort -u "$BASELINE") | grep -c . || true)
new_kb_gaps=$(comm -23 log/kb_gaps.txt <(sort -u "$KB_BASELINE") | grep -c . || true)

if [[ "$new_failures" -gt 0 ]]; then
  note ""
  note "### NEW failures this run"
  comm -23 "$CURRENT" <(sort -u "$BASELINE") | sed 's/^/- /' >> "$REPORT"
fi
known=$(comm -12 "$CURRENT" <(sort -u "$BASELINE") | grep -c . || true)
if [[ "$known" -gt 0 ]]; then
  note ""
  note "### Known failures, still failing ($known)"
  comm -12 "$CURRENT" <(sort -u "$BASELINE") | sed 's/^/- /' >> "$REPORT"
fi
if [[ "$new_kb_gaps" -gt 0 ]]; then
  note ""
  note "### NEW knowledge-base gaps"
  comm -23 log/kb_gaps.txt <(sort -u "$KB_BASELINE") | sed 's/^/- /' >> "$REPORT"
fi

note ""
note "RUN_SUMMARY: new_failures=$new_failures new_kb_gaps=$new_kb_gaps layers_ok=$layers_ok/4"

# Failures: this run replaces the baseline. A test that was fixed drops out, so
# if it ever breaks again that counts as new — which it is.
cp "$CURRENT" "$BASELINE"

# Gaps: accumulate instead of replace. The assistant is non-deterministic, so a
# gap that does not reappear next run is not evidence it was filled — the same
# question has been seen to answer well once and fall back the next time.
# Replacing here would re-report the same shaky topic as "new" every few runs.
# Union means "new" == "never seen before", which is the only honest reading.
sort -u "$KB_BASELINE" log/kb_gaps.txt -o "$KB_BASELINE"

echo ""
echo "RUN_SUMMARY: new_failures=$new_failures new_kb_gaps=$new_kb_gaps layers_ok=$layers_ok/4"
echo "Report appended to $REPORT"

# Non-zero when this run found something new, so a caller that checks $? sees it.
[[ "$new_failures" -eq 0 && "$new_kb_gaps" -eq 0 && "$layers_ok" -eq 4 ]]
