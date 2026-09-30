"""Retention job: keep three tables from growing without end.

    python -m scripts.prune_records

Run by APScheduler alongside the market refresh, or by cron.

Each table here grows on a timer or on a rate-limited endpoint, so none of
them is bounded by anything a user does. None was pruned, which is fine for a
demo and is a slow leak in anything long-lived.

The three are not the same kind of data, and they are treated differently on
purpose.

**`market_snapshots` is a cache.** Only the newest row per symbol is ever
read (`market_repo.latest_snapshot`), and the refresh job writes one per
symbol per interval. Everything older is dead weight, kept only so a
deployment can look back at what the cache held. Deleting it loses nothing a
user can see.

**`password_resets` is spent credentials.** A row exists so that a second use
of a link can be refused rather than read as "no such token", which matters
only while the link could plausibly still be in an inbox. Past expiry plus a
margin it is a hash of a string nobody can use.

**`simulations` is the user's own data**, and that makes its retention a
product decision rather than a maintenance one. The default here is
deliberately far above anything reachable through the product — the list
endpoint pages at 100 and a person runs a handful — so it bounds a runaway
loop without touching a real history. It is a setting, and the number is the
owner's to change. Nothing here deletes a user's most recent runs.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # run as `python scripts/...`

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.logging import configure_logging  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.auth import PasswordReset  # noqa: E402
from app.models.market import MarketSnapshot  # noqa: E402
from app.models.simulation import Simulation  # noqa: E402

log = logging.getLogger("finmentor.retention")


def _as_utc(moment: datetime) -> datetime:
    """SQLite hands back a naive timestamp; treat it as UTC (see market/cache.py)."""
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def prune_market_snapshots(db: Session, keep_per_symbol: int | None = None) -> int:
    """Keep the newest `keep_per_symbol` rows for each symbol.

    Select-then-delete rather than a window function in SQL: the suite runs on
    SQLite and deployments on Postgres, the row counts here are small, and a
    portable query that is obviously correct beats a clever one that behaves
    differently on the two backends.
    """
    keep = settings.retention_market_snapshots_per_symbol if keep_per_symbol is None \
        else keep_per_symbol
    if keep <= 0:
        return 0

    symbols = db.scalars(select(MarketSnapshot.symbol).distinct()).all()
    removed = 0
    for symbol in symbols:
        stale = db.scalars(
            select(MarketSnapshot)
            .where(MarketSnapshot.symbol == symbol)
            .order_by(MarketSnapshot.as_of.desc(), MarketSnapshot.id.desc())
            .offset(keep)
        ).all()
        for row in stale:
            db.delete(row)
            removed += 1
    return removed


def prune_password_resets(db: Session, older_than_days: int | None = None,
                          *, now: datetime | None = None) -> int:
    """Drop resets that expired more than `older_than_days` ago.

    The margin matters. A row is what lets a *second* use of a spent link be
    refused as "no longer valid" rather than read as "never existed", and that
    distinction is worth keeping for as long as somebody might still click the
    link in their inbox. After that it is a hash of a string that cannot be
    spent.
    """
    days = settings.retention_password_reset_days if older_than_days is None \
        else older_than_days
    if days <= 0:
        return 0

    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    rows = db.scalars(select(PasswordReset)).all()
    removed = 0
    for row in rows:
        if _as_utc(row.expires_at) < cutoff:
            db.delete(row)
            removed += 1
    return removed


def prune_simulations(db: Session, keep_per_user: int | None = None) -> int:
    """Keep the newest `keep_per_user` saved runs for each user.

    The user's own data, so the default is a runaway guard rather than a
    retention policy: far above what the product can reach, and the newest
    runs are never the ones removed. See the module docstring.
    """
    keep = settings.retention_simulations_per_user if keep_per_user is None \
        else keep_per_user
    if keep <= 0:
        return 0

    user_ids = db.scalars(select(Simulation.user_id).distinct()).all()
    removed = 0
    for user_id in user_ids:
        stale = db.scalars(
            select(Simulation)
            .where(Simulation.user_id == user_id)
            .order_by(Simulation.created_at.desc(), Simulation.id.desc())
            .offset(keep)
        ).all()
        for row in stale:
            db.delete(row)
            removed += 1
    return removed


def prune(db: Session) -> dict[str, int]:
    """Run every retention rule. Returns what each removed. Commits once.

    One failing table must not abort the run, for the same reason the market
    refresh counts failures rather than raising: a job that stops at the first
    problem leaves the rest of the work undone every time.
    """
    counts: dict[str, int] = {}
    for name, rule in (
        ("market_snapshots", prune_market_snapshots),
        ("password_resets", prune_password_resets),
        ("simulations", prune_simulations),
    ):
        try:
            counts[name] = rule(db)
        except Exception:  # noqa: BLE001 - one bad table must not stop the batch
            log.exception("failed to prune %s", name)
            counts[name] = 0
    db.commit()
    return counts


def main() -> int:
    configure_logging()
    with SessionLocal() as db:
        counts = prune(db)
    log.info("retention removed %s", counts)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
