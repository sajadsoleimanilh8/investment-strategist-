"""Market analytics contracts."""
from __future__ import annotations

from pydantic import BaseModel, Field

MARKET_DISCLAIMER = (
    "This information describes recent or historical market behaviour and is "
    "not a prediction or personalised investment recommendation."
)


class TrendReportOut(BaseModel):
    symbol: str
    latest_price: float
    change_1d_pct: float
    change_7d_pct: float
    change_30d_pct: float
    moving_average_short: float
    moving_average_long: float
    volatility: float
    volatility_label: str      # Low | Medium | High
    trend: str                 # Upward | Downward | Neutral
    disclaimer: str = MARKET_DISCLAIMER


class MarketAssetOut(BaseModel):
    """A known asset. `trend` is filled only from the cache — listing assets
    never triggers a provider call."""

    symbol: str
    display_name: str
    asset_class: str            # crypto | equity
    trend: TrendReportOut | None = None


class AssetListOut(BaseModel):
    items: list[MarketAssetOut]
    disclaimer: str = MARKET_DISCLAIMER


class WatchlistOut(BaseModel):
    items: list[TrendReportOut]
    disclaimer: str = MARKET_DISCLAIMER


class WatchlistIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=24)
