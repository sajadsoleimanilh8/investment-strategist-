from app.market.base import PricePoint
from app.services.market_engine import (
    analyze, classify_trend, moving_average, pct_change_over,
    rank_by_momentum, volatility, volatility_label,
)


def pts(closes):
    return [PricePoint(date=f"2026-01-{i+1:02d}", close=c) for i, c in enumerate(closes)]


def test_moving_average():
    assert moving_average(pts([10, 20, 30]), 3) == 20


def test_pct_change_over_window():
    assert pct_change_over(pts([100, 105, 110]), 1) == round((110 - 105) / 105 * 100, 2)


def test_volatility_constant_is_zero():
    assert volatility(pts([50, 50, 50, 50])) == 0.0


def test_volatility_label_bands():
    assert volatility_label(0.5) == "Low"
    assert volatility_label(2.0) == "Medium"
    assert volatility_label(9.0) == "High"


def test_classify_trend():
    assert classify_trend(110, 100) == "Upward"
    assert classify_trend(90, 100) == "Downward"
    assert classify_trend(100.1, 100) == "Neutral"


def test_analyze_and_rank():
    up = analyze("UP", pts([100, 102, 104, 106, 108, 110, 112, 114]))
    down = analyze("DN", pts([114, 112, 110, 108, 106, 104, 102, 100]))
    assert up.trend == "Upward"
    ranked = rank_by_momentum([down, up])
    assert [r.symbol for r in ranked] == ["UP", "DN"]
