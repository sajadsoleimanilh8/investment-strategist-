"""Seed the known market assets (spec section 11) and the demo watchlist.

Idempotent — rerunning updates the same rows. `seed_demo_user.py` calls both
functions so one command sets up a demonstrable database.

    python -m scripts.seed_market_assets
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # run as `python scripts/...`

from sqlalchemy.orm import Session  # noqa: E402

from app.core.logging import configure_logging  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.repositories import market as market_repo  # noqa: E402

log = logging.getLogger("finmentor.seed")

#: (symbol, provider_id, asset_class, display_name)
ASSETS = [
    ("BTC", "bitcoin", "crypto", "Bitcoin"),
    ("ETH", "ethereum", "crypto", "Ethereum"),
    ("SOL", "solana", "crypto", "Solana"),
    ("AAPL", "AAPL", "equity", "Apple"),
    ("MSFT", "MSFT", "equity", "Microsoft"),
    ("TSLA", "TSLA", "equity", "Tesla"),
    ("NVDA", "NVDA", "equity", "NVIDIA"),
]

#: What the demo user watches, so `/market/watchlist/{id}` is never empty.
DEMO_WATCHLIST = ["BTC", "ETH", "AAPL", "NVDA"]


def seed_market_assets(db: Session) -> int:
    for symbol, provider_id, asset_class, display_name in ASSETS:
        market_repo.upsert_asset(
            db, symbol=symbol, provider_id=provider_id,
            asset_class=asset_class, display_name=display_name,
        )
    return len(ASSETS)


def seed_demo_watchlist(db: Session, user_id: int) -> int:
    for symbol in DEMO_WATCHLIST:
        market_repo.add_to_watchlist(db, user_id, symbol)
    return len(DEMO_WATCHLIST)


def main() -> int:
    configure_logging()
    with SessionLocal() as db:
        count = seed_market_assets(db)
        db.commit()
    log.info("seeded %s market assets", count)
    print(f"market assets seeded: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
