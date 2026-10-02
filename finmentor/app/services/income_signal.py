"""What recorded income says about how steady it is.

Pure arithmetic over a list of amounts, like every other module here: no
session, no ORM row, nothing to mock (docs/ARCHITECTURE.md).

Why this exists at all. `income_type` is asked during onboarding, stored on
the profile, passed into the Financial Twin, and read by nothing: not the
health score, not the budget engine, not the DNA. It is a question the
product asks and then ignores. Meanwhile `income_records` was declared in the
initial schema with a docstring calling it "the signal behind
`income_type = variable`", and nothing ever wrote a row to it.

So the two halves of one idea were both present and neither was connected.
This is the half that computes.

**It does not overwrite what the user said.** `assess` returns an
observation, and the declared value stays exactly as the user set it. Two
reasons, and the second is the real one:

1. Nothing reads `income_type`, so deriving it would change no figure
   anywhere. It would be a write with no effect.
2. The moment something *does* read it, a silent derivation would move every
   existing user's numbers without them asking. "Your records look variable,
   you have this set to fixed" is a sentence the user can act on; a changed
   score they did not ask for is not.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass

#: Below this many recorded periods, variation is noise and this says so
#: rather than classifying. Two months differing is not a pattern, and the
#: product would be stating one.
MIN_PERIODS = 3

#: Coefficient of variation (standard deviation over the mean), and the two
#: cuts across it.
#:
#: These are judgement, not measurement, so they are constants with their
#: reasoning attached rather than magic numbers in a branch. Under 5% is a
#: salary with a rounding difference. Over 25% is a month that can be a third
#: short of another, which is the thing an emergency fund exists for. The
#: middle is real variation that is not the whole story.
FIXED_BELOW = 0.05
VARIABLE_ABOVE = 0.25


@dataclass(frozen=True)
class IncomeSignal:
    """What the records show, and whether they show enough to say."""

    #: Recorded periods the figure is computed from.
    periods: int
    #: True when there are too few periods to classify. Everything below is
    #: then a best effort and `suggested` is None.
    insufficient: bool
    mean: float
    low: float
    high: float
    #: Standard deviation over the mean. None when the mean is zero, because
    #: the ratio is undefined rather than large.
    variation: float | None
    #: `fixed`, `variable`, `mixed`, or None when there is not enough to say.
    #: Never written to the profile. See the module docstring.
    suggested: str | None


def assess(amounts: list[float]) -> IncomeSignal:
    """Classify a series of recorded monthly incomes.

    The coefficient of variation rather than the raw spread, because the
    spread is not comparable between people: 500 of swing is most of a small
    income and a rounding error on a large one, and a measure that calls the
    first steady and the second volatile has it backwards.
    """
    usable = [amount for amount in amounts if amount is not None]
    if not usable:
        return IncomeSignal(periods=0, insufficient=True, mean=0.0, low=0.0,
                            high=0.0, variation=None, suggested=None)

    mean = statistics.fmean(usable)
    low, high = min(usable), max(usable)

    # `pstdev` rather than `stdev`: these are the months the user has, not a
    # sample drawn from an infinite population of their months, and `stdev`
    # on a single value raises rather than returning zero.
    variation = (statistics.pstdev(usable) / mean) if mean > 0 else None

    insufficient = len(usable) < MIN_PERIODS or variation is None
    return IncomeSignal(
        periods=len(usable),
        insufficient=insufficient,
        mean=mean,
        low=low,
        high=high,
        variation=variation,
        suggested=None if insufficient else _classify(variation),
    )


def _classify(variation: float) -> str:
    if variation < FIXED_BELOW:
        return "fixed"
    if variation > VARIABLE_ABOVE:
        return "variable"
    return "mixed"


def disagrees_with(signal: IncomeSignal, declared: str) -> bool:
    """Is the user's declared `income_type` at odds with their records?

    False whenever there is not enough to say, which is the common case and
    the one where a prompt would be noise. False, too, when the declared
    value is not one this module knows: an unrecognised value is not a
    disagreement, it is a different problem.
    """
    if signal.insufficient or signal.suggested is None:
        return False
    if declared not in ("fixed", "variable", "mixed"):
        return False
    return signal.suggested != declared
