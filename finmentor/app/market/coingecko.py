"""Crypto provider (CoinGecko market_chart, no key needed).

Ported from legacy data/market_data.fetch_crypto_daily.

**Not verified against the live API.** Same as the equities provider: needs
network, so it is a pre-deploy manual step (docs/ROADMAP.md, Phase 8). The
fallback to mock is tested; the live response shape is not.
"""
from __future__ import annotations

from datetime import datetime

import requests

from app.core.config import settings
from app.market.base import MarketDataProvider, PricePoint

_COMMON = {"btc": "bitcoin", "eth": "ethereum", "sol": "solana"}


class CoinGeckoProvider(MarketDataProvider):
    name = "coingecko"

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
