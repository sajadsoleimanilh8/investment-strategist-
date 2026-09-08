"""Provider-agnostic market data abstraction (spec section 11)."""
from __future__ import annotations

import abc
from dataclasses import dataclass


@dataclass
class PricePoint:
    date: str            # ISO date "2026-08-27"
    close: float
    volume: float | None = None


class MarketDataProvider(abc.ABC):
    """All providers return plain list[PricePoint] so analytics never sees
    provider-specific shapes."""

    name: str = "base"

    @abc.abstractmethod
    def supports(self, symbol: str) -> bool:
        ...

    @abc.abstractmethod
    def get_daily_series(self, symbol: str, days: int = 30) -> list[PricePoint]:
        ...
