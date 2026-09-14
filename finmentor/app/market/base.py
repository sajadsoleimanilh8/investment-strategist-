"""Provider-agnostic market data abstraction (spec section 11)."""
from __future__ import annotations

import abc
from dataclasses import dataclass


@dataclass
class PricePoint:
    date: str            # ISO date "2026-08-27"
    close: float
    volume: float | None = None


@dataclass
class Spot:
    """A current price, as opposed to a daily close.

    Separate from `PricePoint` because it is a different measurement: a close
    is a settled figure for a finished day, a spot is "what it costs right
    now", and merging them would let one be rendered as the other.
    """
    symbol: str
    price_usd: float
    change_24h_pct: float | None
    as_of: float         # unix seconds


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

    #: Whether `get_spot` does anything. Declared rather than discovered,
    #: because the caller picks a provider before it has a symbol to try.
    supports_spot: bool = False

    def get_spot(self, symbols: list[str]) -> dict[str, Spot]:
        """Current price per symbol, for the live ticker.

        Not abstract: spot is a second, optional capability, and forcing every
        provider to implement it would mean writing a stub for the equities
        provider that no caller has a use for. A provider that leaves
        `supports_spot` False is never asked.
        """
        raise NotImplementedError(f"{self.name} has no spot endpoint")
