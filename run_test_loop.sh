#!/usr/bin/env bash
# Keeps the tester agent running until it's actually satisfied: all 4 layers OK,
# zero new failures, zero new KB gaps, for REQUIRED_CLEAN_RUNS in a row.
# One clean run can be luck (flaky test, server just happened to be warm) —
# requiring several in a row is what makes "satisfied" mean something.

set -uo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

MAX_ITERATIONS="${MAX_ITERATIONS:-50}"
REQUIRED_CLEAN_RUNS="${REQUIRED_CLEAN_RUNS:-3}"
SLEEP_BETWEEN="${SLEEP_BETWEEN:-20}"
SESSION_TIMEOUT="${SESSION_TIMEOUT:-1800}"
REPORT="log/test_report.md"

mkdir -p log log/kb_drafts

iteration=0
clean_streak=0
structural_failures=0

while (( iteration < MAX_ITERATIONS )); do
  iteration=$((iteration + 1))
  echo "=== Iteration $iteration/$MAX_ITERATIONS — $(date) ==="

  if ! timeout "$SESSION_TIMEOUT" opencode run --agent tester \
      "Run a full QA pass: Django tests, API smoke tests, UI flows, and knowledge-base gap check. Report only NEW failures and new KB gaps vs the last run. End with a RUN_SUMMARY line." ; then
    structural_failures=$((structural_failures + 1))
    echo "Agent run itself failed/timed out (streak: $structural_failures) — not a test result, something's broken structurally."
    clean_streak=0
    if (( structural_failures >= 5 )); then
      echo "5 broken agent runs in a row — stopping for human review. Check opencode/env setup, not the app."
      exit 1
    fi
    sleep "$SLEEP_BETWEEN"
    continue
  fi
  structural_failures=0

  # Pull the last RUN_SUMMARY line the agent wrote.
  summary_line="$(grep "^RUN_SUMMARY:" "$REPORT" | tail -1)"
  if [[ -z "$summary_line" ]]; then
    echo "No RUN_SUMMARY line found in $REPORT — agent didn't follow the report format. Treating as not clean."
    clean_streak=0
    sleep "$SLEEP_BETWEEN"
    continue
  fi

  new_failures=$(echo "$summary_line" | grep -oP 'new_failures=\K[0-9]+' || echo 999)
  new_kb_gaps=$(echo "$summary_line" | grep -oP 'new_kb_gaps=\K[0-9]+' || echo 999)
  layers_ok=$(echo "$summary_line" | grep -oP 'layers_ok=\K[0-9]+' || echo 0)

  echo "Result: new_failures=$new_failures new_kb_gaps=$new_kb_gaps layers_ok=$layers_ok/4"

  if [[ "$new_failures" -eq 0 && "$new_kb_gaps" -eq 0 && "$layers_ok" -eq 4 ]]; then
    clean_streak=$((clean_streak + 1))
    echo "Clean run ($clean_streak/$REQUIRED_CLEAN_RUNS needed)"
  else
    clean_streak=0
    echo "Not clean — streak reset. New bugs/gaps to review in $REPORT and log/kb_drafts/."
  fi

  if (( clean_streak >= REQUIRED_CLEAN_RUNS )); then
    echo ""
    echo "=== SATISFIED: $REQUIRED_CLEAN_RUNS consecutive clean runs. Stopping. ==="
    echo "Review $REPORT and log/kb_drafts/ for anything still open, then commit."
    exit 0
  fi

  sleep "$SLEEP_BETWEEN"
done

echo "Reached MAX_ITERATIONS ($MAX_ITERATIONS) without $REQUIRED_CLEAN_RUNS consecutive clean runs."
echo "This means real, persistent issues — check $REPORT and log/kb_drafts/ rather than raising the limit."
exit 1
