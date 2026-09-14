#!/usr/bin/env bash
# Run the test suite against the versions that actually ship.
#
#   scripts/check_pinned.sh
#
# The local environment and requirements.txt agree today. They have not always:
# twelve packages once differed, `fastapi` by twenty-four minor versions, and
# everything `pytest` said was a statement about versions no user would run.
#
# That is not hypothetical. Twice now a name that exists in the newer library
# and not the pinned one has shipped and broken a user-facing path:
#
#   Phase 8  `def logout() -> None` on a 204 route — the container would not
#            start at all, caught by building the image
#   later    `status.HTTP_422_UNPROCESSABLE_CONTENT` in the error handlers —
#            every validation error became a 500 in the container, and every
#            local test said it was fine
#
# Both were invisible to `pytest` and obvious here. This runs the same suite
# inside the API image, where the pins are what is installed.
#
# Tests are not baked into the image (.dockerignore keeps them out, correctly),
# so they are mounted, along with the few repo files some tests read.
#
# Exits 2 and says why if Docker is unavailable. A machine without Docker should
# not go red for a check it cannot perform — but it must not report a pass
# either, because the check did not run.
set -uo pipefail

cd "$(dirname "$0")/.."
REPO="$(pwd -W 2>/dev/null || pwd)"

# Exit 2, not 0. A skip here is not a pass: it means the one check that looks at
# the versions users actually get did not run, and saying "passed" would be a
# lie of omission. The caller decides what to do with that — `ci_demo.sh`
# reports the gate as incomplete and fails it under --strict.
if ! docker info >/dev/null 2>&1; then
  echo "  SKIPPED: Docker is not available, so the pinned versions were NOT"
  echo "  exercised. Local pytest tests whatever this machine has installed,"
  echo "  which is not necessarily what ships. This check did not run."
  exit 2
fi

echo "building the API image…"
if ! docker compose build api >/dev/null 2>&1; then
  echo "  FAILED: the image would not build"
  exit 1
fi

echo "running the suite against the pinned versions…"
docker run --rm \
  -v "/${REPO}/tests:/app/tests" \
  -v "/${REPO}/pytest.ini:/app/pytest.ini" \
  -v "/${REPO}/.coveragerc:/app/.coveragerc" \
  -v "/${REPO}/.env.example:/app/.env.example" \
  -v "/${REPO}/requirements.txt:/app/requirements.txt" \
  -v "/${REPO}/docker-compose.yml:/app/docker-compose.yml" \
  -e DEMO_MODE=true \
  -e ENABLE_SCHEDULER=false \
  -e LOCAL_LLM_PROVIDER=fake \
  -e AUTH_RATE_LIMIT_PER_MINUTE=0 \
  -e ASK_RATE_LIMIT_PER_MINUTE=0 \
  --entrypoint python finmentor-api -m pytest -q --tb=short -p no:cacheprovider "$@"
status=$?

if [[ $status -eq 0 ]]; then
  echo "  passed — the code works on the versions it ships with"
else
  echo "  FAILED — this passes locally and fails on the pinned versions."
  echo "  Either the pin is wrong or the code uses something the pin does not have."
fi
exit $status
