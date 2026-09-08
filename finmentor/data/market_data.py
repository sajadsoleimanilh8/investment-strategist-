"""
Market data layer.

Pulls raw price series for stocks (Alpha Vantage) and crypto (CoinGecko),
both of which have free tiers that need no paid plan for a prototype.

Every fetch function returns a plain list[PricePoint] so the analysis layer
never has to know which provider the data came from. If the network call
fails (rate limit, no internet, bad key) each function falls back to
`generate_mock_series` so the rest of the bot keeps working during a demo.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
import random
from typing import List, Optional

import requests

from config import settings


@dataclass
class PricePoint:
    date: str  # ISO date, e.g. "2026-08-27"
    close: float
    volume: Optional[float] = None


def generate_mock_series(symbol: str, days: int = 30, start_price: float = 100.0) -> List[PricePoint]:
    """Deterministic-ish mock series so the bot is demoable with no API key
    and no internet (e.g. during a competition offline demo)."""
    rng = random.Random(symbol)  # seeded by symbol -> stable across runs
    price = start_price
    points: List[PricePoint] = []
    today = datetime.utcnow().date()
    for i in range(days, 0, -1):
        drift = rng.uniform(-0.03, 0.035)
        price = max(0.5, price * (1 + drift))
        date = (today - timedelta(days=i)).isoformat()
        points.append(PricePoint(date=date, close=round(price, 2), volume=rng.uniform(1e5, 1e6)))
    return points


def fetch_stock_daily(symbol: str, days: int = 30) -> List[PricePoint]:
    """Daily close prices for a stock symbol via Alpha Vantage TIME_SERIES_DAILY."""
    url = "https://www.alphavantage.co/query"
    params = {
        "function": "TIME_SERIES_DAILY",
        "symbol": symbol,
        "apikey": settings.alpha_vantage_api_key,
        "outputsize": "compact",
    }
    try:
        resp = requests.get(url, params=params, timeout=8)
        resp.raise_for_status()
        payload = resp.json()
        series = payload.get("Time Series (Daily)")
        if not series:
            raise ValueError(f"Unexpected Alpha Vantage response: {payload}")
        points = [
            PricePoint(date=date, close=float(values["4. close"]), volume=float(values["5. volume"]))
            for date, values in series.items()
        ]
        points.sort(key=lambda p: p.date)
        return points[-days:]
    except Exception:
        # Network unreachable, rate-limited, or bad key -> keep the demo alive.
        return generate_mock_series(symbol, days=days)


def fetch_crypto_daily(coin_id: str, days: int = 30) -> List[PricePoint]:
    """Daily close prices for a coin via CoinGecko's free market_chart endpoint."""
    url = f"{settings.coingecko_base_url}/coins/{coin_id}/market_chart"
    params = {"vs_currency": "usd", "days": days, "interval": "daily"}
    try:
        resp = requests.get(url, params=params, timeout=8)
        resp.raise_for_status()
        payload = resp.json()
        prices = payload.get("prices", [])
        if not prices:
            raise ValueError(f"Unexpected CoinGecko response: {payload}")
        points = [
            PricePoint(date=datetime.utcfromtimestamp(ts / 1000).date().isoformat(), close=round(price, 2))
            for ts, price in prices
        ]
        return points
    except Exception:
        return generate_mock_series(coin_id, days=days, start_price=random.Random(coin_id).uniform(1, 60000))


def fetch_watchlist(stock_symbols: List[str], crypto_ids: List[str], days: int = 30) -> dict:
    """Convenience wrapper: fetch the whole configured watchlist in one call.
    Returns {"AAPL": [PricePoint, ...], "bitcoin": [PricePoint, ...], ...}."""
    result = {}
    for symbol in stock_symbols:
        result[symbol] = fetch_stock_daily(symbol, days=days)
    for coin_id in crypto_ids:
        result[coin_id] = fetch_crypto_daily(coin_id, days=days)
    return result
