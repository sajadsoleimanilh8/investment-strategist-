#!/usr/bin/env bash
# The DEMO_MODE gate: both surfaces, nothing external reachable.
#
#   scripts/ci_demo.sh
#
# What a deploy should be blocked on. It runs, in order:
#
#   1. the test suite, with a 100% floor on app/services — the deterministic
#      core, where an untested branch is a wrong number on a dashboard
#   2. the Definition-of-Done flow through the engine and the Telegram pipeline
#      (scripts/demo_check.py), with Ollama pointed at a closed port
#   3. the same flow through a browser (Playwright), against an API whose model
#      host is equally closed
#   4. the suite again, inside the API image, against the versions in
#      requirements.txt. The local environment matches those pins today, but it
#      has drifted twice before, and each time a name present in the newer
#      library and absent from the pinned one shipped and broke a user-facing
#      path. This is what notices when they part company again.
#
# The model being *unreachable* rather than faked is the point of steps 2 and 3.
# A fake provider would let both pass while proving nothing about the promise
# that matters: the figures are computed before any model is involved, so the
# model going away costs the prose and not the numbers.
#
# Step 3 skips rather than fails when no browser is installed — see
# web/scripts/e2e.mjs. Pass --strict to make that a failure too.
set -uo pipefail

cd "$(dirname "$0")/.."

STRICT=""
[[ "${1:-}" == "--strict" ]] && STRICT="--strict"

failed=0
skipped=0
step() {
  printf '\n\033[1m==> %s\033[0m\n' "$1"
}

step "1/4  tests, with the app/services coverage floor"
if python -m pytest --cov --cov-fail-under=100 -q; then
  echo "    passed"
else
  echo "    FAILED"
  failed=1
fi

step "2/4  Definition-of-Done flow — engine + bot pipeline, no network"
if python scripts/demo_check.py; then
  echo "    passed"
else
  echo "    FAILED"
  failed=1
fi

step "3/4  the same flow in a browser"
if (cd web && npm run test:e2e -- e2e/flow.spec.ts ${STRICT:+-- --strict}); then
  echo "    passed"
else
  echo "    FAILED"
  failed=1
fi

step "4/4  the suite against the versions that actually ship"
bash scripts/check_pinned.sh
case $? in
  0) echo "    passed" ;;
  # 2 means Docker was unavailable, so the check did not run. That is not a
  # pass and must not be reported as one — the gate stays green on a machine
  # without Docker, but says out loud that it is incomplete.
  2) echo "    DID NOT RUN"
     skipped=1
     [[ -n "$STRICT" ]] && { echo "    --strict: an unrun check is a failure"; failed=1; } ;;
  *) echo "    FAILED"; failed=1 ;;
esac

printf '\n%s\n' "======================================================================"
if [[ $failed -ne 0 ]]; then
  echo "DEMO_MODE gate FAILED — see above."
elif [[ $skipped -ne 0 ]]; then
  echo "DEMO_MODE gate passed, but INCOMPLETE: one or more checks did not run."
  echo "Re-run with Docker available, or use --strict to make that a failure."
else
  echo "DEMO_MODE gate passed: both surfaces work with no Ollama, no market API,"
  echo "and no remote LLM."
fi
exit $failed
