import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from data.market_data import PricePoint
from analysis.technical_indicators import (
    analyze,
    classify_trend,
    moving_average,
    pct_change,
    rank_watchlist,
    volatility,
)


def make_points(closes):
    return [PricePoint(date=f"2026-01-{i+1:02d}", close=c) for i, c in enumerate(closes)]


def test_moving_average_basic():
    points = make_points([10, 20, 30])
    assert moving_average(points, window=3) == 20


def test_moving_average_window_larger_than_data():
    points = make_points([10, 20])
    assert moving_average(points, window=5) == 15


def test_pct_change_up():
    points = make_points([100, 110])
    assert pct_change(points) == 10.0


def test_pct_change_flat_when_single_point():
    points = make_points([100])
    assert pct_change(points) == 0.0


def test_volatility_zero_for_constant_prices():
    points = make_points([50, 50, 50, 50])
    assert volatility(points) == 0.0


def test_volatility_nonzero_for_moving_prices():
    points = make_points([50, 55, 48, 60])
    assert volatility(points) > 0


def test_classify_trend_up_down_sideways():
    assert classify_trend(short_ma=110, long_ma=100) == "uptrend"
    assert classify_trend(short_ma=90, long_ma=100) == "downtrend"
    assert classify_trend(short_ma=100.1, long_ma=100) == "sideways"


def test_analyze_end_to_end():
    points = make_points([100, 102, 105, 108, 110, 112, 115])
    report = analyze("TEST", points, short_window=3, long_window=7)
    assert report.symbol == "TEST"
    assert report.latest_price == 115
    assert report.trend_label in {"uptrend", "downtrend", "sideways"}


def test_rank_watchlist_orders_by_momentum():
    a = analyze("A", make_points([100, 90]))   # -10%
    b = analyze("B", make_points([100, 120]))  # +20%
    c = analyze("C", make_points([100, 100]))  # 0%
    ranked = rank_watchlist([a, b, c])
    assert [r.symbol for r in ranked] == ["B", "C", "A"]
