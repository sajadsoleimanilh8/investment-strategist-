"""The public market surfaces: the live WebSocket and the series that seeds
its sparkline.

Public is the interesting part. These two are the only routes under `/api`
that answer without a token, so what is tested here is mostly what they refuse
to do: serve a cross-origin page, accept unbounded connections, reach a
provider, or answer for a symbol the landing page does not tick.
"""
from __future__ import annotations

import pytest
from starlette.websockets import WebSocketDisconnect

from app.api.routes import market_live
from app.core.config import settings

ALLOWED_ORIGIN = "http://localhost:5173"


# --- the WebSocket --------------------------------------------------------

def test_a_client_is_told_the_feed_is_off_rather_than_left_waiting(raw_client):
    """Under MARKET_LIVE_SOURCE=off (what this suite runs with) the first and
    only frame says so, which is what lets the page render a static panel
    instead of a spinner that never resolves."""
    with raw_client.websocket_connect(
        "/api/market/live", headers={"origin": ALLOWED_ORIGIN}
    ) as socket:
        frame = socket.receive_json()

    assert frame["type"] == "snapshot"
    assert frame["status"] == "off"
    assert frame["ticks"] == {}


def test_a_socket_from_another_origin_is_refused(raw_client):
    """A WebSocket upgrade does not pass through CORS, so without this check
    any page on the internet could open a connection here."""
    with pytest.raises(WebSocketDisconnect):
        with raw_client.websocket_connect(
            "/api/market/live", headers={"origin": "http://evil.example"}
        ) as socket:
            socket.receive_json()


def test_a_client_with_no_origin_is_allowed(raw_client):
    """Browsers always send Origin on a handshake, so a request without one is
    a server-side client and not the cross-site risk the check exists for."""
    with raw_client.websocket_connect("/api/market/live") as socket:
        assert socket.receive_json()["type"] == "snapshot"


def test_connections_are_capped(raw_client, monkeypatch):
    monkeypatch.setattr(market_live, "MAX_LIVE_CLIENTS", 0)

    with pytest.raises(WebSocketDisconnect):
        with raw_client.websocket_connect("/api/market/live") as socket:
            socket.receive_json()


def test_a_disconnect_leaves_no_client_behind(raw_client):
    with raw_client.websocket_connect("/api/market/live"):
        pass

    assert market_live.hub.clients == set()


def test_the_allowed_origins_are_the_api_s_own(raw_client):
    """One list, not two: the socket and the HTTP API agree on who may call."""
    assert market_live.origin_allowed(settings.cors_origins[0]) is True
    assert market_live.origin_allowed("http://elsewhere.example") is False


# --- the public series ----------------------------------------------------

def test_the_public_series_needs_no_token(raw_client):
    response = raw_client.get("/api/market/public/BTC")

    assert response.status_code == 200
    assert response.json()["symbol"] == "BTC"


def test_a_cold_cache_answers_with_an_empty_series_rather_than_fetching(raw_client):
    """Cache-only by design: an unauthenticated route that could reach a
    provider is a way for anyone to spend the free-tier budget."""
    body = raw_client.get("/api/market/public/ETH").json()

    assert body["points"] == []
    assert body["disclaimer"]


def test_it_serves_only_the_symbols_the_landing_page_ticks(raw_client):
    """Not a public door onto the whole market surface: the watchlist and the
    asset list stay behind require_user."""
    assert raw_client.get("/api/market/public/AAPL").status_code == 404


def test_the_symbol_is_case_insensitive(raw_client):
    assert raw_client.get("/api/market/public/btc").status_code == 200
