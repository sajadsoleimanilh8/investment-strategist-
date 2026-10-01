"""Deterministic synthetic series. Used when DEMO_MODE=true or a real
provider is unreachable, so the product is never visibly broken offline.

Ported from legacy data/market_data.generate_mock_series.
"""
from __future__ import annotations

import random
import time
from datetime import datetime, timedelta, timezone

from app.market.base import MarketDataProvider, PricePoint, Spot


class MockMarketProvider(MarketDataProvider):
    name = "mock"
    supports_spot = True

    def supports(self, symbol: str) -> bool:
        return True

    def get_daily_series(self, symbol: str, days: int = 30) -> list[PricePoint]:
        rng = random.Random(symbol)               # seeded => stable across runs
        start_price = rng.uniform(20, 40000)
        price = start_price
        points: list[PricePoint] = []
        # `now(timezone.utc)`, not `utcnow()`: the latter is a naive
        # datetime pretending to be UTC and is deprecated for it.
        today = datetime.now(timezone.utc).date()
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

    #: How often the synthetic spot price is allowed to change. Seeding on a
    #: bucket rather than on the clock is what keeps it deterministic: two
    #: processes asking inside the same bucket get the same number, which is
    #: what "deterministic synthetic data" has to mean for a demo to be
    #: repeatable.
    SPOT_BUCKET_SECONDS = 20

    def get_spot(self, symbols: list[str]) -> dict[str, Spot]:
        """A price that moves, without pretending to be a real one.

        The live ticker is a moving figure by definition, so a spot frozen at
        one value would look broken rather than offline. This jitters a seeded
        base price by a couple of percent per bucket so the demo ticks, and
        every surface rendering it is required to label it as demo data: a
        synthetic price shown as a real one is the one thing this project must
        never do.
        """
        now = time.time()
        bucket = int(now // self.SPOT_BUCKET_SECONDS)
        spots: dict[str, Spot] = {}
        for symbol in symbols:
            base = random.Random(symbol).uniform(20, 40000)
            rng = random.Random(f"{symbol}:{bucket}")
            spots[symbol] = Spot(
                symbol=symbol,
                price_usd=round(base * (1 + rng.uniform(-0.02, 0.02)), 2),
                change_24h_pct=round(rng.uniform(-6, 6), 3),
                as_of=now,
            )
        return spots
