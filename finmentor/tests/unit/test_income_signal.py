"""The income-steadiness measure.

Pure arithmetic, so these are about the judgement in it rather than the
plumbing: when there is enough to say anything, where the cuts fall, and what
happens at the edges that make a ratio undefined.
"""
from __future__ import annotations

import pytest

from app.services import income_signal
from app.services.income_signal import (
    FIXED_BELOW, MIN_PERIODS, VARIABLE_ABOVE, assess, disagrees_with,
)


def test_no_records_says_so_rather_than_dividing_by_nothing():
    signal = assess([])

    assert signal.periods == 0
    assert signal.insufficient is True
    assert signal.suggested is None
    assert signal.variation is None


@pytest.mark.parametrize("count", [1, 2])
def test_too_few_periods_refuses_to_classify(count):
    """Two months differing is not a pattern, and saying it is would be the
    product stating one it cannot see."""
    signal = assess([1000.0] * count)

    assert signal.periods == count
    assert signal.insufficient is True
    assert signal.suggested is None


def test_the_threshold_is_three_periods():
    assert MIN_PERIODS == 3
    assert assess([1000.0] * 3).insufficient is False


def test_an_identical_salary_is_fixed():
    signal = assess([3000.0, 3000.0, 3000.0, 3000.0])

    assert signal.variation == 0.0
    assert signal.suggested == "fixed"
    assert signal.mean == 3000.0
    assert (signal.low, signal.high) == (3000.0, 3000.0)


def test_a_rounding_difference_is_still_fixed():
    """A salary that lands on 2999 one month has not become variable."""
    signal = assess([3000.0, 2999.0, 3001.0, 3000.0])

    assert signal.variation < FIXED_BELOW
    assert signal.suggested == "fixed"


def test_a_third_of_a_month_of_swing_is_variable():
    """The case an emergency fund exists for."""
    signal = assess([3000.0, 1200.0, 4500.0, 2000.0])

    assert signal.variation > VARIABLE_ABOVE
    assert signal.suggested == "variable"


def test_real_but_moderate_variation_is_mixed():
    signal = assess([3000.0, 3200.0, 2800.0, 3400.0])

    assert FIXED_BELOW <= signal.variation <= VARIABLE_ABOVE
    assert signal.suggested == "mixed"


def test_the_spread_is_relative_not_absolute():
    """500 of swing is most of a small income and nothing on a large one.

    A measure using the raw spread would call the big earner volatile and the
    small one steady, which is backwards. This is the reason for the
    coefficient of variation and the test that pins it.
    """
    small = assess([500.0, 1000.0, 750.0])
    large = assess([100_000.0, 100_500.0, 100_250.0])

    # The same 500 of swing, classified at opposite ends.
    assert small.high - small.low == large.high - large.low == 500.0
    assert small.suggested == "variable"
    assert large.suggested == "fixed"


def test_a_zero_mean_leaves_the_ratio_undefined_rather_than_large():
    """Dividing by zero is not "infinitely variable", it is unanswerable."""
    signal = assess([0.0, 0.0, 0.0])

    assert signal.variation is None
    assert signal.insufficient is True
    assert signal.suggested is None


def test_a_single_zero_month_is_counted_not_dropped():
    """A month of no income is a real and important data point."""
    signal = assess([3000.0, 0.0, 3000.0])

    assert signal.periods == 3
    assert signal.low == 0.0
    assert signal.suggested == "variable"


def test_a_single_period_does_not_raise():
    """`statistics.stdev` raises on one value; `pstdev` returns zero.

    These are the months the user has, not a sample drawn from a population
    of their months, so the population form is also the correct one.
    """
    signal = assess([2500.0])

    assert signal.variation == 0.0
    assert signal.insufficient is True, "one period is still too few to classify"


# --- the observation, not the correction ---------------------------------

@pytest.mark.parametrize("declared, amounts, expected", [
    ("fixed", [3000.0, 3000.0, 3000.0], False),
    ("fixed", [3000.0, 1000.0, 5000.0], True),
    ("variable", [3000.0, 1000.0, 5000.0], False),
    ("variable", [3000.0, 3000.0, 3000.0], True),
    ("mixed", [3000.0, 3200.0, 2800.0], False),
])
def test_disagreement_is_what_the_records_say_against_what_was_declared(
    declared, amounts, expected
):
    assert disagrees_with(assess(amounts), declared) is expected


def test_too_little_data_is_never_a_disagreement():
    """The common case, and the one where a prompt would be noise."""
    assert disagrees_with(assess([3000.0, 1000.0]), "fixed") is False


def test_an_unrecognised_declared_value_is_not_a_disagreement():
    """An unexpected value is a different problem, not this one."""
    assert disagrees_with(assess([3000.0, 3000.0, 3000.0]), "whatever") is False


def test_assess_never_returns_a_value_to_write():
    """The field is called `suggested` and that is the whole point.

    Nothing reads `income_type` today, so deriving it would be a write with
    no effect. The moment something does read it, a silent derivation would
    move every existing user's figures without them asking.
    """
    signal = assess([3000.0, 1000.0, 5000.0])

    assert not hasattr(signal, "income_type")
    assert signal.suggested == "variable"


def test_the_module_reaches_no_persistence():
    """Same rule as every other service: pure arithmetic, nothing to mock."""
    import ast
    import pathlib

    source = pathlib.Path(income_signal.__file__).read_text(encoding="utf-8")
    imports = {
        name.name.split(".")[0]
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Import)
        for name in node.names
    } | {
        (node.module or "").split(".")[0]
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom)
    }

    assert "sqlalchemy" not in imports
    assert not any(name.startswith("app") for name in imports if name)
