"""Scheduled market refresh job (spec section 24). Run by APScheduler or cron.

Warms `market_snapshots` for every active asset so user requests are served
from the cache and never wait on a provider.

    python -m scripts.fetch_market_snapshots
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # run as `python scripts/...`

from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.logging import configure_logging  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.market import cache  # noqa: E402
from app.repositories import market as market_repo  # noqa: E402
from app.services import market_engine  # noqa: E402

log = logging.getLogger("finmentor.market")

DEFAULT_DAYS = 30


def symbols_to_refresh(db: Session) -> list[str]:
    """Active assets if the table is seeded, else the configured watchlists.

    The fallback keeps the job useful on a database that has not been seeded
    yet — an empty asset table should not silently refresh nothing.
    """
    seeded = [asset.symbol for asset in market_repo.list_active_assets(db)]
    if seeded:
        return seeded
    return [s.upper() for s in (*settings.stock_watchlist, *settings.crypto_watchlist)]


def refresh(db: Session, *, days: int = DEFAULT_DAYS) -> dict[str, int]:
    """Fetch and store one series per symbol. Returns a {refreshed, failed} count.

    One unreachable provider must not abort the run, so failures are counted
    and logged rather than raised — the cache keeps whatever it already had.
    """
    refreshed = failed = 0
    for symbol in symbols_to_refresh(db):
        try:
            points = market_engine.get_series(symbol, days=days)
            cache.store_series(db, symbol, points)
            refreshed += 1
        except Exception:  # noqa: BLE001 - a bad symbol must not stop the batch
            log.exception("failed to refresh %s", symbol)
            failed += 1
    db.commit()
    return {"refreshed": refreshed, "failed": failed}


def main() -> int:
    configure_logging()
    with SessionLocal() as db:
        counts = refresh(db)
    log.info(
        "market snapshots refreshed=%s failed=%s (demo_mode=%s)",
        counts["refreshed"], counts["failed"], settings.demo_mode,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
