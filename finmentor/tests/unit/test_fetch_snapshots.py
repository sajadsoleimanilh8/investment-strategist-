"""The scheduled refresh job — and proof the scheduler stays dormant in tests."""
import pytest

from app.core.config import settings
from app.market import cache
from app.repositories import market as market_repo
from scripts import fetch_market_snapshots
from scripts.seed_market_assets import seed_market_assets


@pytest.fixture
def assets(db):
    seed_market_assets(db)
    db.commit()


def test_refresh_populates_a_snapshot_per_active_asset(db, assets):
    counts = fetch_market_snapshots.refresh(db)

    symbols = [asset.symbol for asset in market_repo.list_active_assets(db)]
    assert counts == {"refreshed": len(symbols), "failed": 0}
    for symbol in symbols:
        snapshot = market_repo.latest_snapshot(db, symbol)
        assert snapshot is not None
        assert len(cache.decode_points(snapshot.points_json)) == 30


def test_a_refreshed_symbol_is_served_from_the_cache_afterwards(db, assets, monkeypatch):
    fetch_market_snapshots.refresh(db)

    from app.services import market_engine

    calls = []
    monkeypatch.setattr(market_engine, "get_series", lambda *a, **k: calls.append(a) or [])

    points = cache.get_or_fetch(db, "BTC", days=30)

    assert calls == [], "the scheduled job should have warmed this"
    assert len(points) == 30


def test_symbols_fall_back_to_the_configured_watchlists(db):
    """An unseeded asset table must not mean refreshing nothing."""
    assert market_repo.list_active_assets(db) == []

    symbols = fetch_market_snapshots.symbols_to_refresh(db)

    expected = {s.upper() for s in (*settings.stock_watchlist, *settings.crypto_watchlist)}
    assert set(symbols) == expected
    assert symbols, "the fallback must not be empty"


def test_seeded_assets_win_over_the_configured_watchlists(db, assets):
    symbols = fetch_market_snapshots.symbols_to_refresh(db)
    assert set(symbols) == {a.symbol for a in market_repo.list_active_assets(db)}


def test_one_bad_symbol_does_not_abort_the_batch(db, assets, monkeypatch):
    from app.services import market_engine

    real = market_engine.get_series

    def flaky(symbol, days=30):
        if symbol == "ETH":
            raise RuntimeError("provider exploded")
        return real(symbol, days=days)

    monkeypatch.setattr(market_engine, "get_series", flaky)
    counts = fetch_market_snapshots.refresh(db)

    assert counts["failed"] == 1
    assert counts["refreshed"] == len(market_repo.list_active_assets(db)) - 1
    assert market_repo.latest_snapshot(db, "ETH") is None
    assert market_repo.latest_snapshot(db, "BTC") is not None


def test_refresh_is_repeatable(db, assets):
    fetch_market_snapshots.refresh(db)
    first = market_repo.latest_snapshot(db, "BTC")

    fetch_market_snapshots.refresh(db)
    second = market_repo.latest_snapshot(db, "BTC")

    assert second.id != first.id                 # a new row, newest wins
    assert second.as_of >= first.as_of


def test_the_scheduler_is_disabled_under_pytest():
    """tests/conftest.py sets ENABLE_SCHEDULER=false before the app is imported."""
    assert settings.enable_scheduler is False


def test_the_app_starts_without_a_scheduler(client):
    # the `client` fixture runs the lifespan; with the flag off nothing is started
    assert client.get("/healthz").json()["status"] == "ok"
