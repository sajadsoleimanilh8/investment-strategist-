"""The live-price hub, and the promises it makes about what it will not do.

The provider is a fake throughout: this suite is about the hub's behaviour
when a provider succeeds, fails, or is switched off, none of which needs a
network. The live CoinGecko shape stays a pre-deploy manual check
(docs/PRE_DEPLOY.md), same as every other provider in this project.
"""
from __future__ import annotations

import asyncio

import pytest

from app.core.config import Settings
from app.market import live
from app.market.base import MarketDataProvider, Spot
from app.market.coingecko import CoinGeckoProvider
from app.market.mock_provider import MockMarketProvider


class FakeProvider(MarketDataProvider):
    """Returns what it is told to, and counts how often it was asked."""

    name = "fake"
    supports_spot = True

    def __init__(self, prices: dict[str, float] | None = None, fail: bool = False):
        self.prices = prices or {"BTC": 100.0}
        self.fail = fail
        self.calls = 0

    def supports(self, symbol: str) -> bool:
        return True

    def get_daily_series(self, symbol: str, days: int = 30):  # pragma: no cover
        raise NotImplementedError

    def get_spot(self, symbols: list[str]) -> dict[str, Spot]:
        self.calls += 1
        if self.fail:
            raise RuntimeError("provider is down")
        return {
            symbol: Spot(symbol=symbol, price_usd=price, change_24h_pct=1.5, as_of=0.0)
            for symbol, price in self.prices.items()
        }


class FakeSocket:
    """Enough of a WebSocket for the hub: accept, send, and a record of both."""

    def __init__(self, fail_on_send: bool = False):
        self.accepted = False
        self.sent: list[dict] = []
        self.fail_on_send = fail_on_send

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, payload: dict) -> None:
        if self.fail_on_send:
            raise RuntimeError("socket gone")
        self.sent.append(payload)


@pytest.fixture
def hub():
    return live.LiveMarketHub()


# --- what the hub does with a working provider ---------------------------

@pytest.mark.asyncio
async def test_a_poll_stores_and_returns_only_what_moved(hub):
    provider = FakeProvider({"BTC": 100.0, "ETH": 50.0})
    hub._provider = provider

    first = await hub._poll_once()
    assert set(first) == {"BTC", "ETH"}          # everything is new the first time

    provider.prices["ETH"] = 51.0
    second = await hub._poll_once()

    assert set(second) == {"ETH"}, "an unchanged price is not a tick"
    assert hub.latest["BTC"].price_usd == 100.0
    assert hub.latest["ETH"].price_usd == 51.0


@pytest.mark.asyncio
async def test_a_newcomer_gets_the_current_snapshot_immediately(hub):
    hub._provider = FakeProvider()
    await hub._poll_once()
    socket = FakeSocket()

    await hub.register(socket)

    assert socket.accepted
    assert socket.sent[0]["type"] == "snapshot"
    assert socket.sent[0]["ticks"]["BTC"]["price_usd"] == 100.0


@pytest.mark.asyncio
async def test_a_socket_that_fails_to_send_is_dropped(hub):
    socket = FakeSocket(fail_on_send=True)
    await hub.register(socket)

    await hub._broadcast({"type": "status", "status": "live"})

    assert socket not in hub.clients


# --- the promises ---------------------------------------------------------

@pytest.mark.asyncio
async def test_a_failing_provider_never_falls_back_to_synthetic_prices(hub):
    """The whole point of the panel is that the number is real. A provider
    outage must show as an outage, not as a mock price under a live label."""
    hub._provider = FakeProvider(fail=True)

    with pytest.raises(RuntimeError):
        await hub._poll_once()

    assert hub.latest == {}, "nothing was invented to fill the gap"


def test_demo_mode_resolves_a_live_source_to_off():
    """DEMO_MODE promises the product runs with nothing external reachable, so
    a live poll would sit on 'reconnecting' for the length of the demo."""
    assert Settings(demo_mode=True, market_live_source="live").effective_market_live_source == "off"


def test_demo_mode_still_allows_an_explicit_mock_source():
    """Asking for synthetic ticks is a deliberate act, and the client labels
    that panel as demo data."""
    assert Settings(demo_mode=True, market_live_source="mock").effective_market_live_source == "mock"


def test_a_source_of_off_starts_no_poll_task(hub, monkeypatch):
    monkeypatch.setattr(live.settings, "demo_mode", True)
    monkeypatch.setattr(live.settings, "market_live_source", "live")

    hub.start()

    assert hub._task is None
    assert hub.status == "off" and hub.source == "off"


def test_the_provider_follows_the_configured_source(monkeypatch):
    monkeypatch.setattr(live.settings, "demo_mode", False)

    monkeypatch.setattr(live.settings, "market_live_source", "mock")
    assert isinstance(live.build_spot_provider(), MockMarketProvider)

    monkeypatch.setattr(live.settings, "market_live_source", "live")
    assert isinstance(live.build_spot_provider(), CoinGeckoProvider)


@pytest.mark.asyncio
async def test_the_poll_loop_parks_while_nobody_is_watching(hub, monkeypatch):
    """An instance with no visitors spends no provider calls at all."""
    provider = FakeProvider()
    hub._provider = provider
    monkeypatch.setattr(live, "POLL_INTERVAL_SECONDS", 0.01)

    task = asyncio.create_task(hub._poll_forever())
    await asyncio.sleep(0.05)
    assert provider.calls == 0, "polled with an empty room"

    await hub.register(FakeSocket())
    await asyncio.sleep(0.05)
    polled_while_watched = provider.calls
    assert polled_while_watched > 0

    hub.unregister(next(iter(hub.clients)))
    await asyncio.sleep(0.05)
    # One more poll may already have been in flight when the last client left;
    # what matters is that it stops, not that it stops on the exact tick.
    assert provider.calls <= polled_while_watched + 1

    task.cancel()


# --- the mock provider's spot --------------------------------------------

def test_the_mock_spot_is_deterministic_within_a_bucket():
    provider = MockMarketProvider()

    first = provider.get_spot(["BTC"])["BTC"].price_usd
    second = provider.get_spot(["BTC"])["BTC"].price_usd

    assert first == second, "a demo has to be repeatable"


def test_the_mock_spot_moves_between_buckets(monkeypatch):
    provider = MockMarketProvider()

    prices = set()
    for bucket in range(6):
        monkeypatch.setattr(
            "time.time", lambda b=bucket: b * MockMarketProvider.SPOT_BUCKET_SECONDS)
        prices.add(provider.get_spot(["BTC"])["BTC"].price_usd)

    assert len(prices) > 1, "a ticker that never ticks looks broken, not offline"


def test_a_provider_without_spot_says_so():
    from app.market.alpha_vantage import AlphaVantageProvider

    assert AlphaVantageProvider().supports_spot is False
    with pytest.raises(NotImplementedError):
        AlphaVantageProvider().get_spot(["AAPL"])
