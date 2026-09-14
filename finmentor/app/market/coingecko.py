"""Crypto provider (CoinGecko market_chart, no key needed).

Ported from legacy data/market_data.fetch_crypto_daily.

**Not verified against the live API.** Same as the equities provider: needs
network, so it is a pre-deploy manual step (docs/ROADMAP.md, Phase 8). The
fallback to mock is tested; the live response shape is not.
"""
from __future__ import annotations

import time
from datetime import datetime

import requests

from app.core.config import settings
from app.market.base import MarketDataProvider, PricePoint, Spot

_COMMON = {"btc": "bitcoin", "eth": "ethereum", "sol": "solana"}


class CoinGeckoProvider(MarketDataProvider):
    name = "coingecko"
    supports_spot = True

    def supports(self, symbol: str) -> bool:
        return symbol.lower() in _COMMON or symbol.islower()

    def get_daily_series(self, symbol: str, days: int = 30) -> list[PricePoint]:
        coin_id = _COMMON.get(symbol.lower(), symbol.lower())
        url = f"{settings.coingecko_base_url}/coins/{coin_id}/market_chart"
        resp = requests.get(
            url, params={"vs_currency": "usd", "days": days, "interval": "daily"}, timeout=8
        )
        resp.raise_for_status()
        prices = resp.json().get("prices", [])
        if not prices:
            raise ValueError(f"unexpected CoinGecko response for {coin_id}")
        return [
            PricePoint(
                date=datetime.utcfromtimestamp(ts / 1000).date().isoformat(),
                close=round(price, 2),
            )
            for ts, price in prices
        ]

    def get_spot(self, symbols: list[str]) -> dict[str, Spot]:
        """Current USD price for several coins in one call.

        `/simple/price` rather than the `market_chart` endpoint above: this is
        the only free-tier call that answers "what is it worth right now"
        without pulling a whole series to read its last point. One request for
        every symbol, which is what keeps the live ticker inside the free
        tier no matter how many browser tabs are watching.
        """
        ids = {symbol: _COMMON.get(symbol.lower(), symbol.lower()) for symbol in symbols}
        resp = requests.get(
            f"{settings.coingecko_base_url}/simple/price",
            params={
                "ids": ",".join(ids.values()),
                "vs_currencies": "usd",
                "include_24hr_change": "true",
            },
            timeout=8,
        )
        resp.raise_for_status()
        body = resp.json()
        now = time.time()

        spots: dict[str, Spot] = {}
        for symbol, coin_id in ids.items():
            entry = body.get(coin_id)
            # A symbol the provider does not know is skipped, not faked. The
            # caller renders what arrived and says nothing about the rest.
            if not entry or entry.get("usd") is None:
                continue
            change = entry.get("usd_24h_change")
            spots[symbol] = Spot(
                symbol=symbol,
                price_usd=round(float(entry["usd"]), 2),
                change_24h_pct=round(float(change), 3) if change is not None else None,
                as_of=now,
            )
        if not spots:
            raise ValueError("CoinGecko returned no recognised symbols")
        return spots
