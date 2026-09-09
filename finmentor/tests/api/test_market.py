"""Market endpoints: assets, one asset's trend, and watchlist CRUD.

Everything runs in DEMO_MODE against the mock provider, so the numbers are
deterministic and no network is touched.
"""
import pytest

from app.repositories import market as market_repo
from app.schemas.market import MARKET_DISCLAIMER
from scripts.seed_market_assets import seed_market_assets


@pytest.fixture
def assets(db):
    seed_market_assets(db)
    db.commit()


@pytest.fixture
def user_id(client, assets) -> int:
    return client.post("/api/users", json={"telegram_id": 810_001}).json()["id"]


# --- assets -------------------------------------------------------------

def test_assets_are_listed_with_their_class(client, assets):
    response = client.get("/api/market/assets")

    assert response.status_code == 200
    body = response.json()
    symbols = {item["symbol"] for item in body["items"]}
    assert {"BTC", "ETH", "SOL", "AAPL", "MSFT", "TSLA", "NVDA"} <= symbols
    assert {item["asset_class"] for item in body["items"]} == {"crypto", "equity"}
    assert body["disclaimer"] == MARKET_DISCLAIMER


def test_listing_assets_does_not_fetch_from_a_provider(client, assets, monkeypatch):
    """Section 24: a list endpoint must never fan out provider calls."""
    from app.services import market_engine

    calls = []
    monkeypatch.setattr(market_engine, "get_series",
                        lambda *a, **k: calls.append(a) or [])

    body = client.get("/api/market/assets").json()

    assert calls == []
    assert all(item["trend"] is None for item in body["items"])   # nothing cached yet


def test_a_listed_asset_shows_its_cached_trend(client, assets, db):
    client.get("/api/market/assets/BTC")            # warms the cache for BTC

    items = {item["symbol"]: item for item in client.get("/api/market/assets").json()["items"]}
    assert items["BTC"]["trend"]["symbol"] == "BTC"
    assert items["BTC"]["trend"]["trend"] in {"Upward", "Downward", "Neutral"}
    assert items["ETH"]["trend"] is None            # never requested, so not cached


def test_an_inactive_asset_is_hidden(client, assets, db):
    market_repo.upsert_asset(db, symbol="SOL", provider_id="solana",
                             asset_class="crypto", is_active=False)
    db.commit()

    symbols = {item["symbol"] for item in client.get("/api/market/assets").json()["items"]}
    assert "SOL" not in symbols


# --- one asset ----------------------------------------------------------

def test_asset_trend_returns_a_full_report(client, assets):
    response = client.get("/api/market/assets/BTC")

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "BTC"
    assert body["latest_price"] > 0
    assert body["trend"] in {"Upward", "Downward", "Neutral"}
    assert body["volatility_label"] in {"Low", "Medium", "High"}
    assert body["disclaimer"] == MARKET_DISCLAIMER


def test_asset_trend_is_deterministic_in_demo_mode(client, assets):
    first = client.get("/api/market/assets/BTC").json()
    second = client.get("/api/market/assets/BTC").json()
    assert first == second


def test_a_lowercase_symbol_still_resolves(client, assets):
    assert client.get("/api/market/assets/btc").json()["symbol"] == "BTC"


def test_an_unknown_symbol_is_404(client, assets):
    response = client.get("/api/market/assets/DOGE")
    assert response.status_code == 404
    assert "DOGE" in response.json()["detail"]


# --- watchlist ----------------------------------------------------------

def test_add_list_and_rank_a_watchlist(client, user_id):
    for symbol in ("BTC", "ETH", "NVDA"):
        added = client.post(f"/api/market/watchlist/{user_id}", json={"symbol": symbol})
        assert added.status_code == 201

    body = client.get(f"/api/market/watchlist/{user_id}").json()
    assert {item["symbol"] for item in body["items"]} == {"BTC", "ETH", "NVDA"}
    assert body["disclaimer"] == MARKET_DISCLAIMER

    changes = [item["change_7d_pct"] for item in body["items"]]
    assert changes == sorted(changes, reverse=True), "ranked by recent momentum"


def test_adding_the_same_symbol_twice_keeps_one_row(client, user_id, db):
    client.post(f"/api/market/watchlist/{user_id}", json={"symbol": "BTC"})
    second = client.post(f"/api/market/watchlist/{user_id}", json={"symbol": "BTC"})

    assert second.status_code == 201                      # idempotent, not an error
    assert len(market_repo.list_watchlist(db, user_id)) == 1


def test_a_symbol_is_stored_upper_case(client, user_id, db):
    client.post(f"/api/market/watchlist/{user_id}", json={"symbol": "btc"})
    assert [item.symbol for item in market_repo.list_watchlist(db, user_id)] == ["BTC"]


def test_an_empty_watchlist_is_an_empty_list(client, user_id):
    body = client.get(f"/api/market/watchlist/{user_id}").json()
    assert body["items"] == []
    assert body["disclaimer"] == MARKET_DISCLAIMER


def test_removing_a_symbol(client, user_id, db):
    client.post(f"/api/market/watchlist/{user_id}", json={"symbol": "BTC"})
    client.post(f"/api/market/watchlist/{user_id}", json={"symbol": "ETH"})

    removed = client.delete(f"/api/market/watchlist/{user_id}/BTC")
    assert removed.status_code == 204

    assert [item.symbol for item in market_repo.list_watchlist(db, user_id)] == ["ETH"]


def test_removing_something_not_watched_is_still_204(client, user_id):
    assert client.delete(f"/api/market/watchlist/{user_id}/BTC").status_code == 204


def test_adding_an_unknown_symbol_is_422(client, user_id):
    response = client.post(f"/api/market/watchlist/{user_id}", json={"symbol": "DOGE"})
    assert response.status_code == 422
    assert "DOGE" in response.json()["detail"]


def test_watchlist_for_an_unknown_user_is_404(client, assets):
    assert client.get("/api/market/watchlist/9999").status_code == 404
    assert client.post("/api/market/watchlist/9999", json={"symbol": "BTC"}).status_code == 404
    assert client.delete("/api/market/watchlist/9999/BTC").status_code == 404


def test_a_warm_watchlist_makes_no_provider_call(client, user_id, monkeypatch):
    for symbol in ("BTC", "ETH"):
        client.post(f"/api/market/watchlist/{user_id}", json={"symbol": symbol})
    client.get(f"/api/market/watchlist/{user_id}")        # warms both symbols

    from app.services import market_engine

    calls = []
    monkeypatch.setattr(market_engine, "get_series",
                        lambda *a, **k: calls.append(a) or [])

    body = client.get(f"/api/market/watchlist/{user_id}").json()

    assert calls == [], "a warm cache must not reach a provider"
    assert len(body["items"]) == 2


def test_every_market_payload_carries_the_disclaimer(client, user_id):
    client.post(f"/api/market/watchlist/{user_id}", json={"symbol": "BTC"})

    payloads = [
        client.get("/api/market/assets").json(),
        client.get("/api/market/assets/BTC").json(),
        client.get(f"/api/market/watchlist/{user_id}").json(),
        client.post(f"/api/market/watchlist/{user_id}", json={"symbol": "ETH"}).json(),
    ]
    assert all(payload["disclaimer"] == MARKET_DISCLAIMER for payload in payloads)
