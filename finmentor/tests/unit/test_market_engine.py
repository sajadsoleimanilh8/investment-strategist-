from app.core.config import settings
from app.market import build_providers
from app.market.base import MarketDataProvider, PricePoint
from app.market.mock_provider import MockMarketProvider
from app.services import market_engine
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

# --- provider selection and fallback ------------------------------------

class BrokenProvider(MarketDataProvider):
    """A provider that is reachable but always fails."""

    name = "broken"

    def supports(self, symbol: str) -> bool:
        return True

    def get_daily_series(self, symbol: str, days: int = 30):
        raise RuntimeError("provider is down")


class EmptyProvider(MarketDataProvider):
    """A provider that answers, but with nothing usable."""

    name = "empty"

    def supports(self, symbol: str) -> bool:
        return True

    def get_daily_series(self, symbol: str, days: int = 30):
        return []


class PickyProvider(MarketDataProvider):
    """A provider that only handles one symbol."""

    name = "picky"

    def supports(self, symbol: str) -> bool:
        return symbol == "ONLY"

    def get_daily_series(self, symbol: str, days: int = 30):
        return pts([1.0, 2.0, 3.0])


def use_providers(monkeypatch, providers):
    monkeypatch.setattr(market_engine, "build_providers", lambda: providers)


def test_a_failing_provider_falls_back_to_mock(monkeypatch):
    use_providers(monkeypatch, [BrokenProvider(), MockMarketProvider()])

    series = market_engine.get_series("BTC", days=10)

    assert len(series) == 10
    assert all(point.close > 0 for point in series)


def test_an_empty_response_falls_back_to_mock(monkeypatch):
    use_providers(monkeypatch, [EmptyProvider(), MockMarketProvider()])

    assert len(market_engine.get_series("BTC", days=5)) == 5


def test_an_unsupported_symbol_skips_to_the_next_provider(monkeypatch):
    use_providers(monkeypatch, [PickyProvider(), MockMarketProvider()])

    picked = market_engine.get_series("ONLY", days=3)
    skipped = market_engine.get_series("BTC", days=3)

    assert [p.close for p in picked] == [1.0, 2.0, 3.0]
    assert len(skipped) == 3                      # mock handled it instead


def test_every_provider_failing_still_returns_mock_data(monkeypatch):
    """The last provider is always the mock, so a demo never breaks."""
    use_providers(monkeypatch, [BrokenProvider(), BrokenProvider(), MockMarketProvider()])

    assert len(market_engine.get_series("BTC", days=7)) == 7


def test_demo_mode_uses_the_mock_provider_only():
    providers = build_providers()

    assert settings.demo_mode is True
    assert [p.name for p in providers] == ["mock"]


def test_mock_series_are_stable_for_a_symbol():
    first = MockMarketProvider().get_daily_series("BTC", days=30)
    second = MockMarketProvider().get_daily_series("BTC", days=30)

    assert [p.close for p in first] == [p.close for p in second]
    assert [p.close for p in first] != [
        p.close for p in MockMarketProvider().get_daily_series("ETH", days=30)
    ]
