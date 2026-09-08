"""
Rule-based technical analysis. Deterministic, no AI, no network — this is
the layer that should be *correct*, not "creative". The AI layers only turn
these numbers into natural-language explanations; they never invent trends.
"""
from dataclasses import dataclass
from statistics import mean, pstdev
from typing import List

from data.market_data import PricePoint


@dataclass
class TrendReport:
    symbol: str
    latest_price: float
    pct_change_period: float       # % change from first to last point in the window
    moving_average_short: float    # e.g. 7-day
    moving_average_long: float     # e.g. 21-day
    volatility: float              # population stdev of daily % returns
    trend_label: str               # "uptrend" | "downtrend" | "sideways"


def _closes(points: List[PricePoint]) -> List[float]:
    return [p.close for p in points]


def moving_average(points: List[PricePoint], window: int) -> float:
    closes = _closes(points)[-window:]
    if not closes:
        return 0.0
    return round(mean(closes), 4)


def pct_change(points: List[PricePoint]) -> float:
    closes = _closes(points)
    if len(closes) < 2 or closes[0] == 0:
        return 0.0
    return round((closes[-1] - closes[0]) / closes[0] * 100, 2)


def daily_returns(points: List[PricePoint]) -> List[float]:
    closes = _closes(points)
    returns = []
    for prev, curr in zip(closes, closes[1:]):
        if prev != 0:
            returns.append((curr - prev) / prev)
    return returns


def volatility(points: List[PricePoint]) -> float:
    returns = daily_returns(points)
    if len(returns) < 2:
        return 0.0
    return round(pstdev(returns) * 100, 3)  # as a %


def classify_trend(short_ma: float, long_ma: float, threshold_pct: float = 0.5) -> str:
    """Simple, explainable trend rule: compare short vs long moving average.
    threshold_pct guards against labeling noise as a trend."""
    if long_ma == 0:
        return "sideways"
    diff_pct = (short_ma - long_ma) / long_ma * 100
    if diff_pct > threshold_pct:
        return "uptrend"
    if diff_pct < -threshold_pct:
        return "downtrend"
    return "sideways"


def analyze(symbol: str, points: List[PricePoint], short_window: int = 7, long_window: int = 21) -> TrendReport:
    if not points:
        raise ValueError(f"No price data for {symbol}")

    short_ma = moving_average(points, short_window)
    long_ma = moving_average(points, min(long_window, len(points)))
    trend = classify_trend(short_ma, long_ma)

    return TrendReport(
        symbol=symbol,
        latest_price=points[-1].close,
        pct_change_period=pct_change(points),
        moving_average_short=short_ma,
        moving_average_long=long_ma,
        volatility=volatility(points),
        trend_label=trend,
    )


def rank_watchlist(reports: List[TrendReport]) -> List[TrendReport]:
    """'Hot assets' ranking = biggest positive momentum first.
    NOTE: this ranks *recent momentum*, it is not a prediction of future
    performance — keep that distinction explicit in any UI copy/disclaimer."""
    return sorted(reports, key=lambda r: r.pct_change_period, reverse=True)
