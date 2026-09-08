from datetime import date

import pytest

from app.schemas.finance import GoalIn
from app.services.goal_engine import (
    MAX_HORIZON_MONTHS, add_months, estimated_completion, months_remaining, progress_pct,
    remaining_amount,
)

TODAY = date(2026, 9, 5)


def goal(target=60_000_000, current=20_000_000, **kwargs) -> GoalIn:
    return GoalIn(name="laptop", target_amount=target, current_amount=current, **kwargs)


def test_progress_pct():
    assert progress_pct(goal(current=0)) == 0.0
    assert progress_pct(goal(current=20_000_000)) == 33.3
    assert progress_pct(goal(current=60_000_000)) == 100.0


def test_progress_never_exceeds_one_hundred():
    assert progress_pct(goal(current=90_000_000)) == 100.0


def test_remaining_amount_floors_at_zero():
    assert remaining_amount(goal()) == 40_000_000
    assert remaining_amount(goal(current=90_000_000)) == 0.0


def test_months_remaining_rounds_up_to_a_whole_month():
    assert months_remaining(goal(), 10_000_000) == 4          # 40M / 10M
    assert months_remaining(goal(), 9_000_000) == 5           # 4.44 -> 5
    assert months_remaining(goal(), 40_000_000) == 1


def test_months_remaining_edges():
    assert months_remaining(goal(current=60_000_000), 1_000) == 0   # already met
    assert months_remaining(goal(), 0) is None                      # saving nothing
    assert months_remaining(goal(), -5_000) is None                 # spending down


def test_estimated_completion_adds_whole_months():
    assert estimated_completion(goal(), 10_000_000, TODAY) == date(2027, 1, 5)


def test_estimated_completion_of_the_demo_goal_at_the_demo_savings_rate():
    # 40M remaining at 10.5M/month -> 4 months
    assert estimated_completion(goal(), 10_500_000, TODAY) == date(2027, 1, 5)


def test_already_met_goal_completes_immediately():
    assert estimated_completion(goal(current=60_000_000), 1_000_000, TODAY) == TODAY


def test_zero_or_negative_contribution_has_no_eta():
    assert estimated_completion(goal(), 0, TODAY) is None
    assert estimated_completion(goal(), -1, TODAY) is None


def test_eta_defaults_to_starting_today():
    eta = estimated_completion(goal(), 40_000_000)
    assert eta is not None and eta > date.today()


def test_add_months_crosses_year_boundaries():
    assert add_months(date(2026, 11, 15), 3) == date(2027, 2, 15)
    assert add_months(date(2026, 1, 1), 12) == date(2027, 1, 1)
    assert add_months(date(2026, 9, 5), 0) == date(2026, 9, 5)


def test_add_months_clamps_to_the_end_of_a_shorter_month():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2028, 1, 31), 1) == date(2028, 2, 29)  # leap year


@pytest.mark.parametrize("contribution", [40_000, 1_000_000, 40_000_000])
def test_eta_is_never_before_the_start(contribution):
    assert estimated_completion(goal(), contribution, TODAY) >= TODAY


def test_a_contribution_too_small_to_ever_finish_has_no_eta():
    # 40M remaining at 1 toman a month is 40M months — not a date, just "no".
    assert months_remaining(goal(), 1) > MAX_HORIZON_MONTHS
    assert estimated_completion(goal(), 1, TODAY) is None


def test_the_horizon_edge_is_still_a_date():
    slow = goal(target=MAX_HORIZON_MONTHS, current=0)
    assert estimated_completion(slow, 1, TODAY) == add_months(TODAY, MAX_HORIZON_MONTHS)
