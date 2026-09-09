"""Market data cache (spec section 24).

Scheduled fetch -> DB -> users. External APIs are never hit on the per-request
path once the cache is warm: a request that finds a fresh snapshot returns it
without constructing a provider at all.

Two things the phase-1 `market_snapshots` table decides for us:

- Snapshots are keyed by symbol alone, with no `days` column. A cached series
  therefore satisfies any request for the same or fewer days; asking for more
  days than were stored is a miss, and the longer series replaces it. That
  keeps the cache correct without a migration.
- `as_of` is a timezone-aware column, but SQLite hands the value back naive.
  `_as_utc` normalises on read so freshness maths works on both backends.

This module is the one place in `app/market` that touches the database — the
providers and the analytics stay persistence-free.

TODO(phase-7): an optional Redis layer in front of this, keyed by
(symbol, days) with the same TTL. DB-backed caching is the requirement; Redis
would only shave the round trip.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.market.base import PricePoint
from app.repositories import market as market_repo
from app.services import market_engine


def _as_utc(moment: datetime) -> datetime:
    """Treat a naive timestamp as UTC (SQLite drops the offset)."""
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def is_fresh(as_of: datetime, *, now: datetime | None = None) -> bool:
    now = now or datetime.now(timezone.utc)
    return now - _as_utc(as_of) < timedelta(seconds=settings.market_cache_ttl_seconds)


def decode_points(points_json: str) -> list[PricePoint]:
    return [PricePoint(**point) for point in json.loads(points_json)]


def get_cached_series(
    db: Session, symbol: str, days: int = 30, *, now: datetime | None = None
) -> list[PricePoint] | None:
    """The newest usable snapshot for `symbol`, or None if there is no hit."""
    snapshot = market_repo.latest_snapshot(db, symbol)
    if snapshot is None or not is_fresh(snapshot.as_of, now=now):
        return None
    points = decode_points(snapshot.points_json)
    return points if len(points) >= days else None


def store_series(db: Session, symbol: str, days: int, points: list[PricePoint]) -> None:
    """Write a fetched series to `market_snapshots`. The caller commits.

    `days` is what was asked for; the stored series is what came back, and its
    length is what later reads compare against.
    """
    market_repo.add_snapshot(
        db,
        symbol=symbol,
        as_of=datetime.now(timezone.utc),
        points_json=json.dumps([point.__dict__ for point in points]),
    )


def get_or_fetch(
    db: Session, symbol: str, days: int = 30, *, now: datetime | None = None
) -> list[PricePoint]:
    """Read-through: a fresh snapshot wins, otherwise fetch and store one."""
    cached = get_cached_series(db, symbol, days, now=now)
    if cached is not None:
        return cached

    points = market_engine.get_series(symbol, days=days)
    store_series(db, symbol, days, points)
    return points
