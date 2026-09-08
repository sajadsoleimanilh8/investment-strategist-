"""Market data cache (spec section 24).

Scheduled fetch -> DB/Redis -> users. External APIs are never hit on the
per-request path once the cache is warm.
# >>> finmentor-stub <<<
"""
from __future__ import annotations

from app.market.base import PricePoint

# TODO(phase-4):
#   - read-through cache keyed by (symbol, days) with settings.market_cache_ttl_seconds
#   - persist to market_snapshots table; optional Redis layer in front
#   - APScheduler job in app/main.py lifespan to refresh the configured watchlists


def get_cached_series(symbol: str, days: int) -> list[PricePoint] | None:
    raise NotImplementedError("phase-4")


def store_series(symbol: str, days: int, points: list[PricePoint]) -> None:
    raise NotImplementedError("phase-4")
