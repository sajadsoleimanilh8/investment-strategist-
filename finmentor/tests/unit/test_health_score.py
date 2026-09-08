import pytest

from app.schemas.finance import ExpenseBreakdown, FinancialProfileIn, GoalIn
from app.services.financial_twin import build_twin
from app.services.health_score import (
    STABILITY_NEUTRAL_POINTS, budget_deviation, compute_health_score, score_budget_stability,
    score_debt_load, score_emergency_fund, score_goal_progress, score_savings_rate,
)

COMPONENT_NAMES = {
    "savings_rate", "emergency_fund", "debt_load", "budget_stability", "goal_progress",
}


def demo_twin(**profile_overrides):
    """The seeded demo user (spec section 29) unless a test says otherwise."""
    data = {
        "monthly_income": 30_000_000,
        "income_type": "mixed",
        "expenses": ExpenseBreakdown(
            housing=8_000_000, food=5_000_000, transportation=2_000_000,
            bills=1_500_000, entertainment=900_000, shopping=600_000,
        ),
        "current_savings": 45_000_000,
        "debt": 10_000_000,
        "monthly_debt_payment": 1_500_000,
        "emergency_fund": 30_000_000,
    }
    data.update(profile_overrides)
    goals = data.pop("goals", [GoalIn(name="laptop", target_amount=60_000_000,
                                      current_amount=20_000_000, priority=1)])
    return build_twin(FinancialProfileIn(**data), goals)


def test_savings_rate_scoring_bounds():
    assert score_savings_rate(0) == 0.0
    assert score_savings_rate(0.25) == 20.0
    assert score_savings_rate(0.5) == 20.0  # clamped


def test_savings_rate_is_linear_in_between():
    assert score_savings_rate(0.125) == 10.0


def test_negative_savings_rate_scores_zero():
    assert score_savings_rate(-0.2) == 0.0


def test_emergency_fund_scoring_bounds():
    assert score_emergency_fund(0) == 0.0
    assert score_emergency_fund(3) == 10.0
    assert score_emergency_fund(6) == 20.0
    assert score_emergency_fund(24) == 20.0


def test_debt_load_scoring():
    assert score_debt_load(0, 1000) == 20.0
    assert score_debt_load(200, 1000) == 10.0
    assert score_debt_load(400, 1000) == 0.0
    assert score_debt_load(900, 1000) == 0.0


def test_debt_load_without_income_scores_zero():
    assert score_debt_load(100, 0) == 0.0


# --- budget stability ---------------------------------------------------

def test_spending_exactly_to_plan_is_full_marks():
    plan = {"housing": 8_000_000, "food": 5_000_000}
    assert score_budget_stability(plan, dict(plan)) == 20.0


def test_small_miss_is_inside_the_tolerance_band():
    plan = {"housing": 8_000_000, "food": 5_000_000}       # 13M planned
    actual = {"housing": 8_000_000, "food": 5_400_000}     # 3.1% over
    assert score_budget_stability(plan, actual) == 20.0


def test_bigger_miss_scores_lower():
    plan = {"housing": 10_000_000}
    assert score_budget_stability(plan, {"housing": 12_000_000}) < 20.0   # 20% over
    assert score_budget_stability(plan, {"housing": 12_000_000}) > 0.0


def test_deviation_at_or_beyond_the_ceiling_scores_zero():
    plan = {"housing": 10_000_000}
    assert score_budget_stability(plan, {"housing": 15_000_000}) == 0.0   # 50% over
    assert score_budget_stability(plan, {"housing": 30_000_000}) == 0.0


def test_underspending_counts_as_deviation_too():
    plan = {"housing": 10_000_000}
    assert score_budget_stability(plan, {"housing": 5_000_000}) == 0.0


def test_category_swaps_are_caught_even_when_the_total_matches():
    plan = {"food": 5_000_000, "shopping": 1_000_000}
    actual = {"food": 1_000_000, "shopping": 5_000_000}
    assert budget_deviation(plan, actual) == pytest.approx(8_000_000 / 6_000_000)
    assert score_budget_stability(plan, actual) == 0.0


def test_no_planned_budget_is_neutral_not_punitive():
    assert budget_deviation(None, {"food": 1}) is None
    assert score_budget_stability(None, {"food": 1}) == STABILITY_NEUTRAL_POINTS
    assert score_budget_stability({}, {"food": 1}) == STABILITY_NEUTRAL_POINTS


def test_stability_accepts_expense_breakdowns_as_well_as_dicts():
    plan = ExpenseBreakdown(housing=8_000_000)
    assert score_budget_stability(plan, ExpenseBreakdown(housing=8_000_000)) == 20.0


# --- goal progress ------------------------------------------------------

def test_no_goals_scores_zero():
    assert score_goal_progress([]) == 0.0


def test_single_goal_scales_with_progress():
    half = GoalIn(name="laptop", target_amount=60_000_000, current_amount=30_000_000)
    assert score_goal_progress([half]) == 10.0


def test_fully_funded_goal_is_full_marks():
    done = GoalIn(name="laptop", target_amount=60_000_000, current_amount=60_000_000)
    assert score_goal_progress([done]) == 20.0


def test_overfunded_goal_does_not_exceed_the_cap():
    over = GoalIn(name="laptop", target_amount=60_000_000, current_amount=200_000_000)
    assert score_goal_progress([over]) == 20.0


def test_high_priority_goals_weigh_more():
    urgent_behind = GoalIn(name="rent", target_amount=100, current_amount=0, priority=1)
    minor_done = GoalIn(name="game", target_amount=100, current_amount=100, priority=5)

    weighted = score_goal_progress([urgent_behind, minor_done])
    # priority 1 weighs 5, priority 5 weighs 1 -> (0*5 + 1*1) / 6 of 20 points
    assert weighted == pytest.approx(20 * (1 / 6), abs=0.05)
    # the same pair with equal priorities would average to half marks
    equal = score_goal_progress([
        GoalIn(name="rent", target_amount=100, current_amount=0, priority=3),
        GoalIn(name="game", target_amount=100, current_amount=100, priority=3),
    ])
    assert equal == 10.0


# --- the assembled score ------------------------------------------------

def test_total_is_the_sum_of_the_five_components():
    score = compute_health_score(demo_twin())

    assert {c.name for c in score.components} == COMPONENT_NAMES
    assert len(score.components) == 5
    assert score.total == pytest.approx(sum(c.points for c in score.components), abs=0.05)


def test_every_component_stays_within_its_twenty_points():
    score = compute_health_score(demo_twin())
    assert all(0 <= c.points <= c.max_points == 20.0 for c in score.components)
    assert 0 <= score.total <= 100


def test_components_carry_a_human_readable_detail():
    score = compute_health_score(demo_twin())
    assert all(c.detail for c in score.components)


def test_demo_user_scores_the_expected_breakdown():
    score = compute_health_score(demo_twin())
    points = {c.name: c.points for c in score.components}

    assert points["savings_rate"] == 20.0          # 35% saved
    assert points["emergency_fund"] == 6.1         # 1.82 months of essentials
    assert points["debt_load"] == 17.5             # 5% of income
    assert points["budget_stability"] == 12.0      # no plan set yet
    assert points["goal_progress"] == 6.7          # laptop at 33%
    assert score.total == 62.3


def test_planned_budget_moves_the_stability_component():
    plan = ExpenseBreakdown(
        housing=8_000_000, food=5_000_000, transportation=2_000_000,
        bills=1_500_000, entertainment=900_000, shopping=600_000,
    )
    score = compute_health_score(demo_twin(planned_budget=plan))
    points = {c.name: c.points for c in score.components}

    assert points["budget_stability"] == 20.0      # spent exactly to plan
    assert score.total == 70.3


def test_zero_income_does_not_divide_by_zero():
    score = compute_health_score(demo_twin(monthly_income=0, goals=[]))

    points = {c.name: c.points for c in score.components}
    assert points["savings_rate"] == 0.0
    assert points["debt_load"] == 0.0
    assert points["goal_progress"] == 0.0
    assert score.total == pytest.approx(sum(c.points for c in score.components), abs=0.05)


def test_empty_profile_scores_the_neutral_floor():
    twin = build_twin(FinancialProfileIn(monthly_income=1))
    score = compute_health_score(twin)

    # nothing saved, no fund, no debt payments, no plan, no goals
    assert {c.name: c.points for c in score.components} == {
        "savings_rate": 20.0,          # income 1, no expenses -> 100% saved
        "emergency_fund": 0.0,
        "debt_load": 20.0,
        "budget_stability": STABILITY_NEUTRAL_POINTS,
        "goal_progress": 0.0,
    }


def test_a_perfect_profile_can_reach_one_hundred():
    plan = ExpenseBreakdown(housing=5_000_000)
    twin = build_twin(
        FinancialProfileIn(
            monthly_income=30_000_000,
            expenses=ExpenseBreakdown(housing=5_000_000),
            planned_budget=plan,
            emergency_fund=30_000_000,          # 6 months of 5M essentials
            monthly_debt_payment=0,
        ),
        [GoalIn(name="done", target_amount=100, current_amount=100)],
    )
    assert compute_health_score(twin).total == 100.0
