"""Live crypto ticker (public, no auth): a small in-process hub that polls a
real provider on an interval and pushes to every connected WebSocket client.

This is deliberately *not* a raw exchange feed. CoinGecko's free tier has no
streaming API, and the free `market_chart` endpoint this project already uses
for historical series (`app.market.coingecko`) is daily-close only — no
intraday candles, no OHLC. So "live" here means: a real, unfaked current
price, refreshed on a short server-side interval and pushed to clients the
moment it changes, which is the honest version of "live" this project's
actual data source can support. `status` on every broadcast tells the
frontend which of these it is looking at, so it is never shown as more than
that.

One hub, module-level: every WebSocket connection shares the same poll
instead of each opening its own, which is what keeps this under CoinGecko's
free-tier rate limit regardless of how many browser tabs are open.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

import httpx
from fastapi import WebSocket

from app.core.config import settings

log = logging.getLogger("finmentor.market.live")

#: symbol -> CoinGecko coin id. Kept in step with `scripts/seed_market_assets.py`
#: and `app.market.coingecko._COMMON` — these are the only crypto assets this
#: project actually knows about.
SYMBOL_TO_COIN_ID = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana"}

POLL_INTERVAL_SECONDS = 20
#: A failed poll retries sooner than a successful one settles, so a blip
#: recovers fast without hammering the provider when it's genuinely down.
RETRY_BACKOFF_SECONDS = 5
MAX_BACKOFF_SECONDS = 60


@dataclass
class Tick:
    symbol: str
    price_usd: float
    change_24h_pct: float | None
    as_of: float  # unix seconds


@dataclass
class LiveMarketHub:
    clients: set[WebSocket] = field(default_factory=set)
    latest: dict[str, Tick] = field(default_factory=dict)
    status: str = "connecting"  # connecting | live | reconnecting
    _task: asyncio.Task | None = field(default=None, repr=False)
    _client: httpx.AsyncClient | None = field(default=None, repr=False)

    def start(self) -> None:
        if self._task is not None:
            return
        self._client = httpx.AsyncClient(timeout=8.0)
        self._task = asyncio.create_task(self._poll_forever(), name="market-live-poll")
        log.info("live market poll started (%ss interval)", POLL_INTERVAL_SECONDS)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def register(self, ws: WebSocket) -> None:
        await ws.accept()
        self.clients.add(ws)
        # A newcomer sees whatever the hub already knows immediately, instead
        # of waiting up to POLL_INTERVAL_SECONDS for the next tick.
        if self.latest:
            await self._send(ws, self._snapshot_payload())

    def unregister(self, ws: WebSocket) -> None:
        self.clients.discard(ws)

    def _snapshot_payload(self) -> dict:
        return {
            "type": "snapshot",
            "status": self.status,
            "ticks": {
                sym: {
                    "symbol": tick.symbol,
                    "price_usd": tick.price_usd,
                    "change_24h_pct": tick.change_24h_pct,
                    "as_of": tick.as_of,
                }
                for sym, tick in self.latest.items()
            },
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
            try:
                await self._poll_once()
                if self.status != "live":
                    self.status = "live"
                    await self._broadcast(self._snapshot_payload())
                backoff = RETRY_BACKOFF_SECONDS
                await asyncio.sleep(POLL_INTERVAL_SECONDS)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # provider down, network error, bad shape
                log.warning("live market poll failed: %s", exc)
                if self.status != "reconnecting":
                    self.status = "reconnecting"
                    await self._broadcast({"type": "status", "status": self.status})
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)

    async def _poll_once(self) -> None:
        assert self._client is not None
        ids = ",".join(SYMBOL_TO_COIN_ID.values())
        resp = await self._client.get(
            f"{settings.coingecko_base_url}/simple/price",
            params={"ids": ids, "vs_currencies": "usd", "include_24hr_change": "true"},
        )
        resp.raise_for_status()
        body = resp.json()
        now = time.time()
        changed: dict[str, Tick] = {}
        for symbol, coin_id in SYMBOL_TO_COIN_ID.items():
            entry = body.get(coin_id)
            if not entry or "usd" not in entry:
                continue
            tick = Tick(
                symbol=symbol,
                price_usd=round(float(entry["usd"]), 2),
                change_24h_pct=(
                    round(float(entry["usd_24h_change"]), 3)
                    if entry.get("usd_24h_change") is not None
                    else None
                ),
                as_of=now,
            )
            previous = self.latest.get(symbol)
            if previous is None or previous.price_usd != tick.price_usd:
                changed[symbol] = tick
            self.latest[symbol] = tick

        if not self.latest:
            raise ValueError("CoinGecko returned no recognised symbols")
        if changed:
            await self._broadcast({
                "type": "ticks",
                "status": "live",
                "ticks": {
                    sym: {
                        "symbol": t.symbol,
                        "price_usd": t.price_usd,
                        "change_24h_pct": t.change_24h_pct,
                        "as_of": t.as_of,
                    }
                    for sym, t in changed.items()
                },
            })


hub = LiveMarketHub()
