"""Rule-based market analytics (spec section 12). Deterministic, no AI.

The trend/indicator maths below are PORTED VERBATIM from the legacy
analysis/technical_indicators.py (already unit-tested) and extended with the
1d/7d/30d windows and volatility labelling the spec asks for.
"""
from __future__ import annotations

from statistics import mean, pstdev

from app.market import PricePoint, build_providers
from app.schemas.market import TrendReportOut


def _closes(points: list[PricePoint]) -> list[float]:
    return [p.close for p in points]


def moving_average(points: list[PricePoint], window: int) -> float:
    closes = _closes(points)[-window:]
    return round(mean(closes), 4) if closes else 0.0


def pct_change_over(points: list[PricePoint], window: int) -> float:
    closes = _closes(points)[-(window + 1):]
    if len(closes) < 2 or closes[0] == 0:
        return 0.0
    return round((closes[-1] - closes[0]) / closes[0] * 100, 2)


def daily_returns(points: list[PricePoint]) -> list[float]:
    closes = _closes(points)
    return [(b - a) / a for a, b in zip(closes, closes[1:]) if a != 0]


def volatility(points: list[PricePoint]) -> float:
    r = daily_returns(points)
    return round(pstdev(r) * 100, 3) if len(r) >= 2 else 0.0


def volatility_label(vol: float) -> str:
    if vol < 1.5:
        return "Low"
    if vol < 4.0:
        return "Medium"
    return "High"


def classify_trend(short_ma: float, long_ma: float, threshold_pct: float = 0.5) -> str:
    if long_ma == 0:
        return "Neutral"
    diff = (short_ma - long_ma) / long_ma * 100
    if diff > threshold_pct:
        return "Upward"
    if diff < -threshold_pct:
        return "Downward"
    return "Neutral"


def analyze(symbol: str, points: list[PricePoint]) -> TrendReportOut:
    if not points:
        raise ValueError(f"no price data for {symbol}")
    short_ma = moving_average(points, 7)
    long_ma = moving_average(points, min(21, len(points)))
    vol = volatility(points)
    return TrendReportOut(
        symbol=symbol,
        latest_price=points[-1].close,
        change_1d_pct=pct_change_over(points, 1),
        change_7d_pct=pct_change_over(points, 7),
        change_30d_pct=pct_change_over(points, 30),
        moving_average_short=short_ma,
        moving_average_long=long_ma,
        volatility=vol,
        volatility_label=volatility_label(vol),
        trend=classify_trend(short_ma, long_ma),
    )


def get_series(symbol: str, days: int = 30) -> list[PricePoint]:
    """Try each provider in order; fall back to mock so a demo never breaks."""
    providers = build_providers()
    for provider in providers:
        if not provider.supports(symbol):
            continue
        try:
            series = provider.get_daily_series(symbol, days=days)
            if series:
                return series
        except Exception:
            continue
    return providers[-1].get_daily_series(symbol, days=days)  # mock is always last


def rank_by_momentum(reports: list[TrendReportOut]) -> list[TrendReportOut]:
    """Ranks RECENT momentum only — not a forecast. Keep that in UI copy."""
    return sorted(reports, key=lambda r: r.change_7d_pct, reverse=True)
