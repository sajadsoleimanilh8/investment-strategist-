"""Deterministic synthetic series. Used when DEMO_MODE=true or a real
provider is unreachable, so the product is never visibly broken offline.

Ported from legacy data/market_data.generate_mock_series.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from app.market.base import MarketDataProvider, PricePoint


class MockMarketProvider(MarketDataProvider):
    name = "mock"

    def supports(self, symbol: str) -> bool:
        return True

    def get_daily_series(self, symbol: str, days: int = 30) -> list[PricePoint]:
        rng = random.Random(symbol)               # seeded => stable across runs
        start_price = rng.uniform(20, 40000)
        price = start_price
        points: list[PricePoint] = []
        today = datetime.utcnow().date()
        for i in range(days, 0, -1):
            price = max(0.5, price * (1 + rng.uniform(-0.03, 0.035)))
            points.append(
                PricePoint(
                    date=(today - timedelta(days=i)).isoformat(),
                    close=round(price, 2),
                    volume=rng.uniform(1e5, 1e6),
                )
            )
        return points
