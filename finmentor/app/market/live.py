"""Live crypto ticker (public, no auth): a small in-process hub that polls the
market provider on an interval and pushes to every connected WebSocket client.

This is deliberately *not* a raw exchange feed. CoinGecko's free tier has no
streaming API, so "live" here means: a real, unfaked current price, refreshed
on a short server-side interval and pushed to clients the moment it changes.
That is the honest version of "live" this project's data source can support,
and `status` on every broadcast tells the frontend which of these it is
looking at, so it is never shown as more than that.

Three things this hub does not do, each for the same reason.

It does not fall back to the mock provider when the real one fails. Everywhere
else in `app/market` that fallback is correct, because a watchlist showing
synthetic history clearly labelled as such beats an error. Here the panel is
headlined "real prices, not a mockup", so a silent swap to synthetic numbers
would turn the page's one verifiable claim into a lie. A failed poll says
"reconnecting" and shows nothing. `MARKET_LIVE_SOURCE=mock` is the supported
way to get synthetic ticks, and the client labels that panel as demo data.

It does not poll while nobody is connected. The loop parks on an event until a
client arrives, which keeps a deployed instance with no visitors off
CoinGecko's free-tier budget entirely.

It does not open a connection per client. One hub, module-level: every
WebSocket shares the same poll, so the provider sees the same request rate
whether one browser tab is watching or a thousand.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from fastapi import WebSocket

from app.core.config import settings
from app.market.base import MarketDataProvider, Spot
from app.market.coingecko import CoinGeckoProvider
from app.market.mock_provider import MockMarketProvider

log = logging.getLogger("finmentor.market.live")

#: The crypto assets the landing page ticks. Kept in step with
#: `scripts/seed_market_assets.py` and `app.market.coingecko._COMMON`.
LIVE_SYMBOLS = ["BTC", "ETH", "SOL"]

POLL_INTERVAL_SECONDS = 20
#: A failed poll retries sooner than a successful one settles, so a blip
#: recovers fast without hammering a provider that is genuinely down.
RETRY_BACKOFF_SECONDS = 5
MAX_BACKOFF_SECONDS = 60


def build_spot_provider() -> MarketDataProvider:
    """The provider behind the ticker, chosen by `MARKET_LIVE_SOURCE`.

    Deliberately not `app.market.build_providers()`: that list is ordered for
    fallback, and fallback is the one thing this surface must not do.
    """
    if settings.effective_market_live_source == "mock":
        return MockMarketProvider()
    return CoinGeckoProvider()


def _as_json(spot: Spot) -> dict:
    return {
        "symbol": spot.symbol,
        "price_usd": spot.price_usd,
        "change_24h_pct": spot.change_24h_pct,
        "as_of": spot.as_of,
    }


@dataclass
class LiveMarketHub:
    clients: set[WebSocket] = field(default_factory=set)
    latest: dict[str, Spot] = field(default_factory=dict)
    #: connecting | live | reconnecting | off
    status: str = "off"
    #: live | mock | off, resolved at start() from settings
    source: str = "off"
    _task: asyncio.Task | None = field(default=None, repr=False)
    _provider: MarketDataProvider | None = field(default=None, repr=False)
    _has_clients: asyncio.Event = field(default_factory=asyncio.Event, repr=False)

    def start(self) -> None:
        self.source = settings.effective_market_live_source
        if self.source == "off" or self._task is not None:
            return
        self.status = "connecting"
        self._provider = build_spot_provider()
        self._task = asyncio.create_task(self._poll_forever(), name="market-live-poll")
        log.info("live market poll started (source=%s, %ss interval)",
                 self.source, POLL_INTERVAL_SECONDS)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._provider = None
        self.status = "off"
        self._has_clients.clear()

    async def register(self, ws: WebSocket) -> None:
        await ws.accept()
        self.clients.add(ws)
        self._has_clients.set()
        # A newcomer gets whatever the hub already knows immediately, rather
        # than waiting up to POLL_INTERVAL_SECONDS for the next tick. When the
        # source is off this is the only frame it will ever receive, and it is
        # what tells the page to render its static panel instead of waiting.
        await self._send(ws, self.snapshot_payload())

    def unregister(self, ws: WebSocket) -> None:
        self.clients.discard(ws)
        if not self.clients:
            self._has_clients.clear()

    def snapshot_payload(self) -> dict:
        return {
            "type": "snapshot",
            "status": self.status,
            "source": self.source,
            "ticks": {symbol: _as_json(spot) for symbol, spot in self.latest.items()},
        }

    async def _send(self, ws: WebSocket, payload: dict) -> None:
        try:
            await ws.send_json(payload)
        except Exception:
            self.unregister(ws)

    async def _broadcast(self, payload: dict) -> None:
        for ws in list(self.clients):
            await self._send(ws, payload)

    async def _poll_forever(self) -> None:
        backoff = RETRY_BACKOFF_SECONDS
        while True:
            # Park until somebody is actually watching. Without this the loop
            # spends a provider call every 20 seconds on an empty room.
            await self._has_clients.wait()
            try:
                changed = await self._poll_once()
                if self.status != "live":
                    self.status = "live"
                    await self._broadcast(self.snapshot_payload())
                elif changed:
                    await self._broadcast({
                        "type": "ticks",
                        "status": "live",
                        "source": self.source,
                        "ticks": {s: _as_json(spot) for s, spot in changed.items()},
                    })
                backoff = RETRY_BACKOFF_SECONDS
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # provider down, network error, bad shape
                log.warning("live market poll failed: %s", exc)
                if self.status != "reconnecting":
                    self.status = "reconnecting"
                    await self._broadcast(
                        {"type": "status", "status": self.status, "source": self.source})
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)

    async def _poll_once(self) -> dict[str, Spot]:
        """Fetch, store, and return only what moved.

        The providers are synchronous (`requests`), so the call goes to a
        thread: blocking the event loop here would stall every connected
        socket for the length of one HTTP request.
        """
        assert self._provider is not None
        spots = await asyncio.to_thread(self._provider.get_spot, LIVE_SYMBOLS)
        changed: dict[str, Spot] = {}
        for symbol, spot in spots.items():
            previous = self.latest.get(symbol)
            if previous is None or previous.price_usd != spot.price_usd:
                changed[symbol] = spot
            self.latest[symbol] = spot
        if not self.latest:
            raise ValueError("provider returned no recognised symbols")
        return changed


hub = LiveMarketHub()
