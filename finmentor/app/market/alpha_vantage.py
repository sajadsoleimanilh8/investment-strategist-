"""Equities provider (Alpha Vantage TIME_SERIES_DAILY).

Ported from legacy data/market_data.fetch_stock_daily. On any failure the
caller (app.services.market_engine) falls back to MockMarketProvider.

**Not verified against the live API.** That needs a real key and network, so it
is a pre-deploy manual step (see docs/ROADMAP.md, Phase 8). The provider loop,
the parsing, and the fallback to mock are covered by tests; what is untested is
whether Alpha Vantage still answers in the shape this expects.
"""
from __future__ import annotations

import requests

from app.core.config import settings
from app.market.base import MarketDataProvider, PricePoint


class AlphaVantageProvider(MarketDataProvider):
    name = "alpha_vantage"
    _URL = "https://www.alphavantage.co/query"

    #: Crypto tickers that look exactly like equity tickers.
    #:
    #: `supports` used to be "all letters, all upper case", which is true of
    #: BTC, ETH and SOL as well as AAPL. In production the provider list is
    #: tried in order, so every crypto refresh spent an Alpha Vantage call —
    #: against a free tier measured in calls per day — before failing through
    #: to CoinGecko, which was always going to answer it.
    #:
    #: A list rather than a lookup, because the shape of a ticker genuinely
    #: does not tell you what it is: `MSTR` is an equity and `BTC` is not, and
    #: nothing about either string says so. Kept in step with
    #: `app.market.coingecko._COMMON` and `scripts/seed_market_assets.py`.
    _NOT_EQUITIES = frozenset({"BTC", "ETH", "SOL"})

    def supports(self, symbol: str) -> bool:
        return (
            symbol.isalpha()
            and symbol.isupper()
            and symbol not in self._NOT_EQUITIES
        )

    def get_daily_series(self, symbol: str, days: int = 30) -> list[PricePoint]:
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": symbol,
            "apikey": settings.alpha_vantage_api_key,
            "outputsize": "compact",
        }
        resp = requests.get(self._URL, params=params, timeout=8)
        resp.raise_for_status()
        series = resp.json().get("Time Series (Daily)")
        if not series:
            raise ValueError(f"unexpected Alpha Vantage response for {symbol}")
        points = [
            PricePoint(date=d, close=float(v["4. close"]), volume=float(v["5. volume"]))
            for d, v in series.items()
        ]
        points.sort(key=lambda p: p.date)
        return points[-days:]
