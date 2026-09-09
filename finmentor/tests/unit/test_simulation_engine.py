"""What-if levers, projection maths, and the before/after deltas."""
import pytest

from app.schemas.finance import ExpenseBreakdown, FinancialProfileIn, GoalIn
from app.schemas.simulation import WhatIfParams
from app.services.financial_twin import build_twin, derive_figures
from app.services.simulation_engine import (
    apply_scenario, primary_goal, project, run_what_if,
)

LAPTOP = GoalIn(name="Laptop", target_amount=60_000_000, current_amount=20_000_000, priority=1)


def demo_twin(goals=(LAPTOP,), **overrides):
    """The seeded demo user: 30M in, 18M out, 1.5M debt payment -> 10.5M saved."""
    data = {
        "monthly_income": 30_000_000,
        "expenses": ExpenseBreakdown(
            housing=8_000_000, food=5_000_000, transportation=2_000_000,
            bills=1_500_000, entertainment=900_000, shopping=600_000,
        ),
        "current_savings": 45_000_000,
        "debt": 10_000_000,
        "monthly_debt_payment": 1_500_000,
        "emergency_fund": 30_000_000,
    }
    data.update(overrides)
    return build_twin(FinancialProfileIn(**data), list(goals))


# --- the shared derived-figures helper ----------------------------------

def test_build_twin_and_derive_figures_agree():
    twin = demo_twin()
    figures = derive_figures(
        income=twin.income, expenses=twin.expenses,
        monthly_debt_payment=twin.monthly_debt_payment, emergency_fund=twin.emergency_fund,
    )
    assert figures.monthly_expenses == twin.monthly_expenses
    assert figures.essential_monthly_expenses == twin.essential_monthly_expenses
    assert figures.monthly_savings == twin.monthly_savings
    assert figures.savings_rate == twin.savings_rate
    assert figures.emergency_months == twin.emergency_months


# --- apply_scenario: one lever at a time --------------------------------

def test_savings_delta_raises_savings_without_touching_income_or_expenses():
    scenario = apply_scenario(demo_twin(), WhatIfParams(monthly_savings_delta=5_000_000))

    assert scenario.monthly_savings == 15_500_000
    assert scenario.income == 30_000_000
    assert scenario.monthly_expenses == 18_000_000
    assert scenario.savings_rate == pytest.approx(15_500_000 / 30_000_000, abs=1e-4)


def test_income_percent_delta_scales_income_and_savings():
    scenario = apply_scenario(demo_twin(), WhatIfParams(income_pct_delta=0.20))

    assert scenario.income == 36_000_000
    assert scenario.monthly_savings == 16_500_000       # +6M income, same outgoings


def test_negative_income_delta_shrinks_savings():
    scenario = apply_scenario(demo_twin(), WhatIfParams(income_pct_delta=-0.10))

    assert scenario.income == 27_000_000
    assert scenario.monthly_savings == 7_500_000


def test_expense_percent_delta_scales_every_category():
    scenario = apply_scenario(demo_twin(), WhatIfParams(expense_pct_delta=0.15))

    assert scenario.monthly_expenses == pytest.approx(20_700_000)
    assert scenario.expenses.housing == pytest.approx(9_200_000)
    assert scenario.monthly_savings == pytest.approx(7_800_000)


def test_category_delta_moves_only_that_category():
    scenario = apply_scenario(
        demo_twin(), WhatIfParams(expense_category_delta={"entertainment": -900_000})
    )

    assert scenario.expenses.entertainment == 0
    assert scenario.expenses.food == 5_000_000
    assert scenario.monthly_expenses == 17_100_000
    assert scenario.monthly_savings == 11_400_000


def test_a_category_can_never_go_negative():
    scenario = apply_scenario(
        demo_twin(), WhatIfParams(expense_category_delta={"food": -99_000_000})
    )
    assert scenario.expenses.food == 0


def test_a_purchase_within_cash_leaves_the_emergency_fund_alone():
    twin = demo_twin()
    scenario = apply_scenario(twin, WhatIfParams(one_time_purchase=40_000_000))

    assert scenario.current_savings == 5_000_000
    assert scenario.emergency_fund == twin.emergency_fund
    assert scenario.emergency_months == twin.emergency_months
    assert scenario.monthly_savings == twin.monthly_savings   # a one-off, not a flow


def test_a_purchase_beyond_cash_eats_into_the_emergency_fund():
    twin = demo_twin()
    scenario = apply_scenario(twin, WhatIfParams(one_time_purchase=60_000_000))

    assert scenario.current_savings == 0                  # all 45M of cash spent
    assert scenario.emergency_fund == 15_000_000          # 15M taken from the fund
    assert scenario.emergency_months < twin.emergency_months


def test_a_purchase_beyond_cash_and_fund_goes_into_the_red():
    scenario = apply_scenario(demo_twin(), WhatIfParams(one_time_purchase=90_000_000))

    assert scenario.current_savings == -15_000_000        # 75M covered, 15M short
    assert scenario.emergency_fund == 0
    assert scenario.emergency_months == 0.0


def test_a_purchase_by_someone_already_in_deficit_still_shows():
    # a profile cannot be created with negative savings, but a scenario can
    # land there, and a second purchase on top must still add up
    broke = demo_twin().model_copy(update={"current_savings": -5_000_000})
    scenario = apply_scenario(broke, WhatIfParams(one_time_purchase=10_000_000))

    # there is no cash to spend, so the whole 10M comes out of the fund
    assert scenario.current_savings == -5_000_000
    assert scenario.emergency_fund == 20_000_000


def test_a_purchase_that_raids_the_fund_lowers_the_health_score():
    from app.services.health_score import compute_health_score

    twin = demo_twin()
    safe = apply_scenario(twin, WhatIfParams(one_time_purchase=40_000_000))
    raiding = apply_scenario(twin, WhatIfParams(one_time_purchase=60_000_000))

    baseline = compute_health_score(twin).total
    assert compute_health_score(safe).total == baseline    # buffer untouched
    assert compute_health_score(raiding).total < baseline


def test_emergency_months_follow_the_scenario_essentials():
    scenario = apply_scenario(demo_twin(), WhatIfParams(expense_pct_delta=1.0))
    # essentials doubled from 16.5M to 33M, so 30M of fund covers less than a month
    assert scenario.emergency_months == pytest.approx(30 / 33, abs=0.01)


def test_levers_combine():
    scenario = apply_scenario(
        demo_twin(),
        WhatIfParams(
            income_pct_delta=0.10,                        # 33M
            expense_pct_delta=-0.10,                      # 16.2M
            expense_category_delta={"shopping": -140_000},
            monthly_savings_delta=1_000_000,
            one_time_purchase=5_000_000,
        ),
    )
    assert scenario.income == pytest.approx(33_000_000)
    assert scenario.monthly_expenses == pytest.approx(16_060_000)
    assert scenario.monthly_savings == pytest.approx(33_000_000 - 16_060_000 - 1_500_000 + 1_000_000)
    assert scenario.current_savings == 40_000_000


def test_the_input_twin_is_never_mutated():
    twin = demo_twin()
    before = twin.model_dump()

    apply_scenario(twin, WhatIfParams(income_pct_delta=0.5, expense_pct_delta=0.5,
                                      monthly_savings_delta=1, one_time_purchase=1))

    assert twin.model_dump() == before


def test_scenario_keeps_the_goals_and_planned_budget():
    twin = demo_twin()
    scenario = apply_scenario(twin, WhatIfParams(monthly_savings_delta=1_000_000))

    assert [g.name for g in scenario.goals] == ["Laptop"]
    assert scenario.planned_budget == twin.planned_budget


# --- a scenario is a proposed plan, not a lapse -------------------------

def on_plan_twin():
    """A user who budgeted and spent exactly to that budget: stability 20/20."""
    plan = ExpenseBreakdown(
        housing=8_000_000, food=5_000_000, transportation=2_000_000,
        bills=1_500_000, entertainment=900_000, shopping=600_000,
    )
    return build_twin(
        FinancialProfileIn(
            monthly_income=30_000_000, expenses=plan, planned_budget=plan,
            current_savings=45_000_000, monthly_debt_payment=1_500_000,
            emergency_fund=30_000_000,
        ),
        [LAPTOP],
    )


def stability_points(twin):
    from app.services.health_score import compute_health_score

    return next(
        component.points for component in compute_health_score(twin).components
        if component.name == "budget_stability"
    )


@pytest.mark.parametrize(
    "params",
    [
        WhatIfParams(expense_pct_delta=-0.15),
        WhatIfParams(expense_pct_delta=0.15),
        WhatIfParams(expense_category_delta={"entertainment": -400_000}),
    ],
)
def test_an_expense_lever_clears_the_plan_instead_of_scoring_a_deviation(params):
    from app.services.health_score import STABILITY_NEUTRAL_POINTS

    twin = on_plan_twin()
    scenario = apply_scenario(twin, params)

    assert stability_points(twin) == 20.0                 # on plan today
    assert scenario.planned_budget is None
    assert stability_points(scenario) == STABILITY_NEUTRAL_POINTS


@pytest.mark.parametrize(
    "params",
    [
        WhatIfParams(income_pct_delta=0.20),
        WhatIfParams(monthly_savings_delta=1_000_000),
        WhatIfParams(one_time_purchase=1_000_000),
    ],
)
def test_non_expense_levers_keep_the_plan_and_the_full_stability_score(params):
    twin = on_plan_twin()
    scenario = apply_scenario(twin, params)

    assert scenario.planned_budget == twin.planned_budget
    assert stability_points(scenario) == 20.0


# --- project ------------------------------------------------------------

def test_projection_is_straight_line():
    result = project(demo_twin(), 6)
    assert result.projected_savings_end == 45_000_000 + 10_500_000 * 6


def test_projection_tracks_the_highest_priority_goal():
    urgent = GoalIn(name="rent", target_amount=100, current_amount=0, priority=1)
    minor = GoalIn(name="game", target_amount=100, current_amount=50, priority=5)

    assert primary_goal(demo_twin(goals=(minor, urgent))).name == "rent"


def test_goal_completion_is_capped_at_one_hundred():
    result = project(demo_twin(), 24)
    assert result.goal_completion_pct == 100.0


def test_goal_completion_at_a_short_horizon():
    # 20M saved + 1 month of 10.5M = 30.5M of a 60M goal
    result = project(demo_twin(), 1)
    assert result.goal_completion_pct == pytest.approx(50.8, abs=0.1)


def test_projection_without_goals_reports_no_goal_figures():
    result = project(demo_twin(goals=()), 12)

    assert result.goal_completion_pct is None
    assert result.estimated_goal_date is None
    assert result.projected_savings_end > 0


def test_an_unreachable_goal_has_no_date_rather_than_a_fake_one():
    broke = demo_twin(monthly_income=18_000_000)      # 1.5M/month short
    result = project(broke, 12)

    assert result.monthly_savings == -1_500_000
    assert result.estimated_goal_date is None
    # the goal erodes rather than grows: 20M - 1.5M*12 = 2M of the 60M target
    assert result.goal_completion_pct == pytest.approx(3.3, abs=0.1)


def test_goal_completion_is_floored_at_zero_never_negative():
    broke = demo_twin(monthly_income=18_000_000)
    result = project(broke, 36)                       # would imply -34M saved

    assert result.goal_completion_pct == 0.0
    assert result.projected_savings_end == 45_000_000 - 1_500_000 * 36


def test_projection_carries_the_label_and_the_health_score():
    from app.services.health_score import compute_health_score

    twin = demo_twin()
    result = project(twin, 12, label="conservative")

    assert result.label == "conservative"
    assert result.health_score == compute_health_score(twin).total


# --- run_what_if --------------------------------------------------------

def test_what_if_reports_both_paths_and_their_deltas():
    out = run_what_if(demo_twin(), WhatIfParams(monthly_savings_delta=5_000_000,
                                                horizon_months=6))

    assert out.current.label == "current"
    assert out.scenario.label == "scenario"
    assert out.deltas["monthly_savings"] == 5_000_000
    assert out.deltas["projected_savings_end"] == 5_000_000 * 6
    assert out.disclaimer


def test_delta_signs_follow_the_lever():
    twin = demo_twin()

    worse = run_what_if(twin, WhatIfParams(expense_pct_delta=0.15))
    better = run_what_if(twin, WhatIfParams(income_pct_delta=0.20))

    assert worse.deltas["monthly_savings"] < 0
    assert worse.deltas["projected_savings_end"] < 0
    assert better.deltas["monthly_savings"] > 0
    assert better.deltas["projected_savings_end"] > 0


def test_a_scenario_that_changes_nothing_has_zero_deltas():
    out = run_what_if(demo_twin(), WhatIfParams())
    assert set(out.deltas.values()) == {0.0}


def test_goal_delta_is_omitted_when_there_is_no_goal():
    out = run_what_if(demo_twin(goals=()), WhatIfParams(monthly_savings_delta=1_000_000))

    assert "goal_completion_pct" not in out.deltas
    assert "monthly_savings" in out.deltas


def test_saving_more_pulls_the_goal_date_forward():
    twin = demo_twin()
    out = run_what_if(twin, WhatIfParams(monthly_savings_delta=5_000_000, horizon_months=6))

    assert out.scenario.estimated_goal_date < out.current.estimated_goal_date


def test_both_paths_track_the_same_goal():
    twin = demo_twin(goals=(LAPTOP, GoalIn(name="car", target_amount=1, priority=5)))
    out = run_what_if(twin, WhatIfParams(monthly_savings_delta=1_000_000))

    # the priority-1 laptop drives both sides, so the percentages are comparable
    assert out.current.goal_completion_pct is not None
    assert out.scenario.goal_completion_pct >= out.current.goal_completion_pct


def test_what_if_runs_inside_the_one_second_budget():
    import time

    twin = demo_twin()
    started = time.perf_counter()
    run_what_if(twin, WhatIfParams(monthly_savings_delta=5_000_000))
    elapsed_ms = (time.perf_counter() - started) * 1000

    assert elapsed_ms < 1000, f"run_what_if took {elapsed_ms:.0f}ms"
