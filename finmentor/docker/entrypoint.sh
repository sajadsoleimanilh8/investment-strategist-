#!/bin/sh
# Migrate, then serve.
#
# `alembic upgrade head` runs here rather than in a human's shell history: a
# container that starts against an out-of-date schema fails in a way that looks
# like an application bug, hours later, on whichever query first touches the
# missing column.
#
# It is safe to run on every boot — `upgrade head` is a no-op once the database
# is current, so a restart or a second replica costs one query.
set -e

echo "waiting for the database…"
python - <<'PY'
import os, time, sys
from sqlalchemy import create_engine, text

url = os.environ["DATABASE_URL"]
deadline = time.time() + 60
while True:
    try:
        create_engine(url, pool_pre_ping=True).connect().execute(text("select 1"))
        print("database is up")
        break
    except Exception as exc:
        if time.time() > deadline:
            print(f"database never came up: {type(exc).__name__}", file=sys.stderr)
            raise SystemExit(1)
        time.sleep(1)
PY

echo "applying migrations…"
alembic upgrade head

if [ "${SEED_DEMO_DATA:-false}" = "true" ]; then
  # Idempotent, and only for a demo stack. Both scripts upsert.
  echo "seeding demo data…"
  python scripts/seed_demo_user.py
  python scripts/seed_market_assets.py
fi

echo "starting: $*"
exec "$@"
