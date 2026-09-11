"""The guards the happy path never reaches.

Each of these was the last uncovered line in `app/services` — a divide-by-zero
check, an empty-input check, a fallback. They exist because the alternative is
a 500 on a real user's dashboard, and the only way to know a guard works is to
stand on it.

Nothing here changes engine logic. These are the inputs that were never fed to
it before.
"""
import pytest

from app.schemas.finance import GoalIn
from app.market.base import PricePoint
from app.services import market_engine
from app.services.health_score import score_goal_progress


def points(*closes: float) -> list[PricePoint]:
    return [PricePoint(date=f"2026-09-{i + 1:02d}", close=close)
            for i, close in enumerate(closes)]


# --- health_score --------------------------------------------------------

def test_goals_that_all_weigh_nothing_score_zero_rather_than_dividing_by_zero():
    """Weight is `6 - priority`, and priority is validated to 1-5, so a total
    of zero cannot happen through the API today. The guard is there for the day
    the priority range changes — `model_construct` skips validation to stand on
    it, which is the only way to reach a defence against invalid input."""
    goals = [GoalIn.model_construct(name="A", target_amount=100.0,
                                    current_amount=50.0, priority=6)]

    assert score_goal_progress(goals) == 0.0


def test_the_priority_weighting_still_favours_the_important_goal():
    """Priority 1 weighs 5x, priority 5 weighs 1x."""
    goals = [
        GoalIn(name="important", target_amount=100.0, current_amount=100.0, priority=1),
        GoalIn(name="minor", target_amount=100.0, current_amount=0.0, priority=5),
    ]

    # 5/6 of the weight is on the finished goal.
    assert score_goal_progress(goals) == round(5 / 6 * 20, 1)


# --- market_engine: change over a window ---------------------------------

def test_a_single_price_point_has_no_change_to_report():
    """A symbol added today has one snapshot. Computing a 7-day change from it
    would be dividing by a window that does not exist."""
    assert market_engine.pct_change_over(points(100.0), window=7) == 0.0


def test_no_price_points_at_all_is_also_zero():
    assert market_engine.pct_change_over(points(), window=7) == 0.0


def test_a_series_that_opens_at_zero_does_not_divide_by_it():
    """A zero open is bad data rather than a 100% gain, and saying "0%" is the
    honest answer to a question that cannot be asked."""
    assert market_engine.pct_change_over(points(0.0, 50.0, 75.0), window=2) == 0.0


# --- market_engine: trend ------------------------------------------------

def test_a_zero_long_average_is_neutral_not_a_crash():
    assert market_engine.classify_trend(short_ma=10.0, long_ma=0.0) == "Neutral"


def test_a_real_pair_still_classifies_normally():
    assert market_engine.classify_trend(short_ma=110.0, long_ma=100.0) == "Upward"
    assert market_engine.classify_trend(short_ma=90.0, long_ma=100.0) == "Downward"
    assert market_engine.classify_trend(short_ma=100.2, long_ma=100.0) == "Neutral"


# --- market_engine: analysing nothing ------------------------------------

def test_analysing_a_symbol_with_no_data_raises_rather_than_inventing():
    """The one place the engine refuses instead of returning a figure. A
    TrendReport full of zeroes would be indistinguishable from a flat market."""
    with pytest.raises(ValueError, match="no price data for DOGE"):
        market_engine.analyze("DOGE", [])


# --- market_engine: the provider fallback --------------------------------

def test_the_last_provider_is_used_when_every_other_one_fails(monkeypatch):
    """Providers are tried in order and the mock is always last, so a dead
    network degrades to seeded data rather than to an error."""
    calls = []

    class Broken:
        def supports(self, symbol): return True

        def get_daily_series(self, symbol, days):
            calls.append("broken")
            raise ConnectionError("network is gone")

    class Mock:
        def supports(self, symbol): return True

        def get_daily_series(self, symbol, days):
            calls.append("mock")
            return points(1.0, 2.0)

    monkeypatch.setattr(market_engine, "build_providers",
                        lambda: [Broken(), Broken(), Mock()])

    series = market_engine.get_series("BTC", days=2)

    assert [p.close for p in series] == [1.0, 2.0]
    assert calls == ["broken", "broken", "mock"]


def test_a_working_provider_short_circuits_the_rest(monkeypatch):
    calls = []

    class Working:
        def supports(self, symbol): return True

        def get_daily_series(self, symbol, days):
            calls.append("working")
            return points(5.0, 6.0)

    class Mock:
        def supports(self, symbol): return True

        def get_daily_series(self, symbol, days):      # pragma: no cover
            calls.append("mock")
            return points(1.0)

    monkeypatch.setattr(market_engine, "build_providers", lambda: [Working(), Mock()])

    market_engine.get_series("BTC", days=2)

    assert calls == ["working"]


def test_the_fallback_fires_when_every_provider_returns_nothing(monkeypatch):
    """The loop `continue`s past an empty result as well as an exception, so a
    symbol no provider recognises falls out of the loop entirely. The last
    provider — the mock, by construction — is then asked directly.

    It is asked a second time, which is mildly wasteful and deliberate: the
    alternative is returning an empty series to a dashboard, and a repeated
    call to seeded local data costs nothing.
    """
    calls = []

    class Empty:
        def supports(self, symbol): return True

        def get_daily_series(self, symbol, days):
            calls.append("empty")
            return []

    monkeypatch.setattr(market_engine, "build_providers", lambda: [Empty(), Empty()])

    assert market_engine.get_series("NOPE", days=2) == []
    # Twice in the loop, once more at the fallback.
    assert calls == ["empty", "empty", "empty"]


def test_a_provider_that_does_not_support_the_symbol_is_skipped(monkeypatch):
    """A crypto provider should never be asked about AAPL."""
    calls = []

    class CryptoOnly:
        def supports(self, symbol): return symbol == "BTC"

        def get_daily_series(self, symbol, days):      # pragma: no cover
            calls.append("crypto")
            return points(9.0)

    class Equities:
        def supports(self, symbol): return True

        def get_daily_series(self, symbol, days):
            calls.append("equities")
            return points(1.0, 2.0)

    monkeypatch.setattr(market_engine, "build_providers", lambda: [CryptoOnly(), Equities()])

    market_engine.get_series("AAPL", days=2)

    assert calls == ["equities"]
