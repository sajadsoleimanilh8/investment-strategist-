#!/usr/bin/env bash
# Run the test suite against the versions that actually ship.
#
#   scripts/check_pinned.sh
#
# The local environment and requirements.txt have drifted apart — twelve
# packages differ, `fastapi` by twenty-four minor versions. Everything `pytest`
# says is therefore a statement about versions no user will ever run.
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
# Exits 0 and says why if Docker is unavailable: a machine without it should
# not go red for a check it cannot perform.
set -uo pipefail

cd "$(dirname "$0")/.."
REPO="$(pwd -W 2>/dev/null || pwd)"

if ! docker info >/dev/null 2>&1; then
  echo "  SKIPPED: Docker is not available, so the pinned versions cannot be"
  echo "  exercised. `pytest` alone tests whatever this machine happens to have"
  echo "  installed, which is not what ships."
  exit 0
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
