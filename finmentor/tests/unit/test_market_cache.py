"""The read-through cache: cold miss fetches once, warm hit fetches never.

Spec section 24 — once the cache is warm, no external call may sit on the
request path. These tests count provider calls to prove it.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings
from app.market import cache
from app.market.base import PricePoint
from app.repositories import market as market_repo

SYMBOL = "BTC"


@pytest.fixture
def counting_fetch(monkeypatch):
    """Wrap `market_engine.get_series` so tests can count provider fetches."""
    from app.services import market_engine

    calls = []
    real = market_engine.get_series

    def counted(symbol, days=30):
        calls.append((symbol, days))
        return real(symbol, days=days)

    monkeypatch.setattr(market_engine, "get_series", counted)
    return calls


def test_a_cold_cache_fetches_once_and_writes_a_row(db, counting_fetch):
    points = cache.get_or_fetch(db, SYMBOL, days=30)

    assert len(counting_fetch) == 1
    assert len(points) == 30
    assert all(isinstance(p, PricePoint) for p in points)

    snapshot = market_repo.latest_snapshot(db, SYMBOL)
    assert snapshot is not None
    assert snapshot.symbol == SYMBOL
    assert len(cache.decode_points(snapshot.points_json)) == 30


def test_a_warm_cache_never_calls_a_provider(db, counting_fetch):
    first = cache.get_or_fetch(db, SYMBOL, days=30)
    counting_fetch.clear()

    for _ in range(5):
        again = cache.get_or_fetch(db, SYMBOL, days=30)

    assert counting_fetch == []            # the whole point of the cache
    assert [p.close for p in again] == [p.close for p in first]


def test_a_stale_snapshot_is_refetched(db, counting_fetch):
    cache.get_or_fetch(db, SYMBOL, days=30)
    counting_fetch.clear()

    stale = datetime.now(timezone.utc) + timedelta(
        seconds=settings.market_cache_ttl_seconds + 60
    )
    cache.get_or_fetch(db, SYMBOL, days=30, now=stale)

    assert len(counting_fetch) == 1
    assert len(market_repo.list_active_assets(db)) == 0   # unrelated table untouched


def test_freshness_is_measured_against_the_configured_ttl():
    now = datetime.now(timezone.utc)
    ttl = settings.market_cache_ttl_seconds

    assert cache.is_fresh(now, now=now)
    assert cache.is_fresh(now - timedelta(seconds=ttl - 1), now=now)
    assert not cache.is_fresh(now - timedelta(seconds=ttl + 1), now=now)


def test_a_naive_timestamp_is_read_as_utc():
    """SQLite drops the offset; freshness maths must still work."""
    now = datetime.now(timezone.utc)
    naive = now.replace(tzinfo=None)

    assert cache.is_fresh(naive, now=now)


def test_asking_for_more_days_than_were_cached_refetches(db, counting_fetch):
    cache.get_or_fetch(db, SYMBOL, days=10)
    counting_fetch.clear()

    longer = cache.get_or_fetch(db, SYMBOL, days=60)

    assert len(counting_fetch) == 1
    assert len(longer) == 60


def test_asking_for_fewer_days_than_were_cached_is_a_hit(db, counting_fetch):
    cache.get_or_fetch(db, SYMBOL, days=60)
    counting_fetch.clear()

    shorter = cache.get_or_fetch(db, SYMBOL, days=7)

    assert counting_fetch == []
    assert len(shorter) == 60          # the stored series, not a truncated copy


def test_get_cached_series_reports_a_miss_rather_than_fetching(db, counting_fetch):
    assert cache.get_cached_series(db, "ETH", days=30) is None
    assert counting_fetch == []


def test_store_series_round_trips_the_points(db):
    points = [PricePoint(date="2026-09-01", close=100.5, volume=1234.0)]
    cache.store_series(db, "SOL", points)

    restored = cache.decode_points(market_repo.latest_snapshot(db, "SOL").points_json)
    assert restored == points


def test_the_newest_snapshot_wins(db):
    older = datetime.now(timezone.utc) - timedelta(seconds=30)
    market_repo.add_snapshot(db, symbol="ETH", as_of=older,
                             points_json='[{"date": "2026-09-01", "close": 1.0}]')
    market_repo.add_snapshot(db, symbol="ETH", as_of=datetime.now(timezone.utc),
                             points_json='[{"date": "2026-09-02", "close": 2.0}]')

    points = cache.get_cached_series(db, "ETH", days=1)
    assert [p.close for p in points] == [2.0]


def test_cached_data_is_deterministic_in_demo_mode(db, counting_fetch):
    """The mock provider is seeded by symbol, so a demo never shifts under you."""
    first = cache.get_or_fetch(db, "AAPL", days=30)
    stale = datetime.now(timezone.utc) + timedelta(
        seconds=settings.market_cache_ttl_seconds + 60
    )
    second = cache.get_or_fetch(db, "AAPL", days=30, now=stale)

    assert [p.close for p in first] == [p.close for p in second]
