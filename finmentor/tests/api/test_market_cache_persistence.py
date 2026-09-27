"""A cache entry a request paid for has to survive the request.

The defect: `GET /api/me/summary` called `market_cache.get_or_fetch`, which on
a miss fetched from the provider and flushed a `market_snapshots` row. The
route never committed, and `get_db` closes its session in `finally` without
committing, so SQLAlchemy discarded the flush. The dashboard called the
provider on every single load and never warmed the cache — which is exactly
what SPEC section 24 says must not happen, hidden behind a cache that appeared
to be working.

Why the rest of the suite could not see it
------------------------------------------
The `client` fixture overrides `get_db` with `lambda: db`, a single session
shared by the request and the assertions. A flushed-but-uncommitted row is
visible inside the session that flushed it, so every existing assertion about
caching passed. The bug only exists across a session boundary.

So this module does not use that fixture. It overrides `get_db` with a real
per-request factory, the way the application does, and inspects the result
from a third session that had no part in the request.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.core import security
from app.db.session import get_db
from app.main import app as fastapi_app
from app.market.base import PricePoint
from app.models.market import MarketSnapshot
from app.repositories import market as market_repo


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sessions(db_engine):
    """A factory that hands out a fresh session, like the application's own."""
    # No `guards.install` here: `app.db.guards` registers the write guards on
    # the `Session` class at import, so every session in the process carries
    # them, this one included.
    return sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)


@pytest.fixture
def realistic_client(sessions) -> TestClient:
    """A client whose requests each get their own session and close it.

    This is the whole point of the module: the shared-session fixture cannot
    reproduce a lost commit, because there is nothing for the commit to cross.
    """
    def per_request_session():
        db = sessions()
        try:
            yield db
        finally:
            db.close()

    fastapi_app.dependency_overrides[get_db] = per_request_session
    try:
        with TestClient(fastapi_app) as test_client:
            yield test_client
    finally:
        fastapi_app.dependency_overrides.clear()


@pytest.fixture
def provider_calls(monkeypatch) -> list[str]:
    """Record every symbol the provider is asked for, and answer deterministically.

    Counting calls is the only way to tell a warm cache from a cold one from
    outside: both produce the same response body.
    """
    calls: list[str] = []

    def fake_series(symbol: str, days: int = 30) -> list[PricePoint]:
        calls.append(symbol)
        return [
            PricePoint(date=f"2026-09-{day:02d}", close=100.0 + day)
            for day in range(1, days + 1)
        ]

    monkeypatch.setattr("app.market.cache.market_engine.get_series", fake_series)
    return calls


@pytest.fixture
def watcher(realistic_client, sessions):
    """A signed-in, onboarded user watching one symbol."""
    pair = realistic_client.post("/api/auth/signup", json={
        "email": "watcher@example.com", "password": "a-long-enough-password"}).json()
    token = pair["access_token"]
    user_id = security.decode_token(token)

    realistic_client.put(f"/api/financial-profile/{user_id}", headers=auth(token), json={
        "monthly_income": 30_000_000,
        "expenses": {"housing": 8_000_000, "food": 5_000_000},
        "emergency_fund": 30_000_000,
    })

    with sessions() as setup:
        market_repo.upsert_asset(setup, symbol="BTC", provider_id="bitcoin",
                                 asset_class="crypto", display_name="Bitcoin")
        setup.commit()

    added = realistic_client.post(f"/api/market/watchlist/{user_id}",
                                  headers=auth(token), json={"symbol": "BTC"})
    assert added.status_code == 201, added.text
    return {"token": token, "user_id": user_id}


def _snapshot_count(sessions) -> int:
    """Read from a session that took no part in any request."""
    with sessions() as observer:
        return observer.query(MarketSnapshot).count()


def test_a_summary_on_a_cold_cache_fetches_and_keeps_what_it_fetched(
    realistic_client, sessions, watcher, provider_calls
):
    """The four steps the defect broke, in order."""
    with sessions() as setup:
        setup.query(MarketSnapshot).delete()
        setup.commit()

    response = realistic_client.get("/api/me/summary", headers=auth(watcher["token"]))

    assert response.status_code == 200, response.text          # 2. it succeeds
    assert provider_calls == ["BTC"]                           # 1. it fetched
    assert _snapshot_count(sessions) == 1                      # 3. and kept it


def test_a_second_summary_does_not_call_the_provider_again(
    realistic_client, sessions, watcher, provider_calls
):
    """4. Once warm, no external call. This is SPEC section 24 in one assert.

    Before the fix this failed with two calls rather than one: the first
    request's snapshot was rolled back when its session closed, so the second
    request found the cache exactly as cold as the first did.
    """
    with sessions() as setup:
        setup.query(MarketSnapshot).delete()
        setup.commit()

    realistic_client.get("/api/me/summary", headers=auth(watcher["token"]))
    calls_after_first = list(provider_calls)

    realistic_client.get("/api/me/summary", headers=auth(watcher["token"]))

    assert provider_calls == calls_after_first, (
        f"the provider was called again on a warm cache: {provider_calls}")
    assert _snapshot_count(sessions) == 1, "a warm read wrote another snapshot"


def test_the_watchlist_route_keeps_its_snapshot_too(
    realistic_client, sessions, watcher, provider_calls
):
    """The fix belongs to the cache, so every read path inherits it.

    `get_watchlist` happened to commit for itself, so it was never broken —
    which is precisely why durability could not stay a per-route convention.
    """
    with sessions() as setup:
        setup.query(MarketSnapshot).delete()
        setup.commit()

    response = realistic_client.get(f"/api/market/watchlist/{watcher['user_id']}",
                                    headers=auth(watcher["token"]))

    assert response.status_code == 200, response.text
    assert _snapshot_count(sessions) == 1
