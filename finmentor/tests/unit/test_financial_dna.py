"""Band boundaries for the Financial DNA (spec section 7).

Bands come from the health-score components, so every case here is expressed
as the twin input that produces a known component score:
Strong >= 14/20, Moderate >= 7/20, Weak below 7/20.
"""
import pytest

from app.schemas.finance import ExpenseBreakdown, FinancialProfileIn, GoalIn
from app.services.financial_dna import (
    ADVANCED_TOPICS, INTERMEDIATE_TOPICS, build_dna, knowledge_level,
)
from app.services.financial_twin import build_twin


def twin(**overrides):
    goals = overrides.pop("goals", [])
    return build_twin(FinancialProfileIn(monthly_income=10_000_000, **overrides), goals)


# --- saving discipline: 20 pts at a 25% rate ----------------------------

@pytest.mark.parametrize(
    ("expenses", "expected"),
    [
        (ExpenseBreakdown(housing=9_500_000), "Weak"),        # 5% rate  -> 4 pts
        (ExpenseBreakdown(housing=8_800_000), "Moderate"),    # 12% rate -> 9.6 pts
        (ExpenseBreakdown(housing=2_500_000), "Strong"),      # 75% rate -> capped 20 pts
    ],
)
def test_saving_discipline_bands(expenses, expected):
    assert build_dna(twin(expenses=expenses)).saving_discipline == expected


def test_saving_discipline_boundary_is_inclusive_at_strong():
    # 14/20 points == a 17.5% savings rate
    at_boundary = twin(expenses=ExpenseBreakdown(housing=8_250_000))
    assert at_boundary.savings_rate == pytest.approx(0.175)
    from app.services.health_score import score_savings_rate

    assert score_savings_rate(at_boundary.savings_rate) == 14.0
    assert build_dna(at_boundary).saving_discipline == "Strong"


# --- emergency readiness: 20 pts at 6 months ----------------------------

@pytest.mark.parametrize(
    ("emergency_fund", "expected"),
    [
        (1_000_000, "Weak"),        # 1 month  -> 3.3 pts
        (3_000_000, "Moderate"),    # 3 months -> 10 pts
        (5_000_000, "Strong"),      # 5 months -> 16.7 pts
    ],
)
def test_emergency_readiness_bands(emergency_fund, expected):
    state = twin(expenses=ExpenseBreakdown(housing=1_000_000), emergency_fund=emergency_fund)
    assert build_dna(state).emergency_readiness == expected


# --- debt management: Strong = comfortably low, well-handled burden -----

@pytest.mark.parametrize(
    ("payment", "expected"),
    [
        (3_000_000, "Weak"),        # 30% of income -> 5 pts
        (2_000_000, "Moderate"),    # 20% -> 10 pts
        (500_000, "Strong"),        # 5%  -> 17.5 pts
    ],
)
def test_debt_management_bands(payment, expected):
    assert build_dna(twin(monthly_debt_payment=payment)).debt_management == expected


# --- goal discipline ----------------------------------------------------

@pytest.mark.parametrize(
    ("current", "expected"),
    [(0, "Weak"), (30, "Weak"), (40, "Moderate"), (70, "Strong"), (100, "Strong")],
)
def test_goal_discipline_bands(current, expected):
    goal = GoalIn(name="g", target_amount=100, current_amount=current)
    assert build_dna(twin(goals=[goal])).goal_discipline == expected


def test_no_goals_reads_as_moderate_not_weak():
    # the neutral 12/20 for "no goals yet" lands in the Moderate band, matching
    # how a missing budget plan is treated
    assert build_dna(twin()).goal_discipline == "Moderate"


# --- budget stability ---------------------------------------------------

def test_budget_stability_without_a_plan_is_moderate():
    # the neutral 12/20 for "no plan set yet" lands in the Moderate band
    assert build_dna(twin(expenses=ExpenseBreakdown(housing=1))).budget_stability == "Moderate"


def test_spending_to_plan_is_strong_budget_stability():
    state = twin(
        expenses=ExpenseBreakdown(housing=5_000_000),
        planned_budget=ExpenseBreakdown(housing=5_000_000),
    )
    assert build_dna(state).budget_stability == "Strong"


def test_ignoring_the_plan_is_weak_budget_stability():
    state = twin(
        expenses=ExpenseBreakdown(housing=9_000_000),
        planned_budget=ExpenseBreakdown(housing=5_000_000),
    )
    assert build_dna(state).budget_stability == "Weak"


# --- financial knowledge ------------------------------------------------

def test_knowledge_level_thresholds():
    assert knowledge_level(0) == "Beginner"
    assert knowledge_level(INTERMEDIATE_TOPICS - 1) == "Beginner"
    assert knowledge_level(INTERMEDIATE_TOPICS) == "Intermediate"
    assert knowledge_level(ADVANCED_TOPICS - 1) == "Intermediate"
    assert knowledge_level(ADVANCED_TOPICS) == "Advanced"
    assert knowledge_level(12) == "Advanced"


def test_knowledge_defaults_to_beginner_when_nothing_is_completed():
    assert build_dna(twin()).financial_knowledge == "Beginner"


def test_knowledge_uses_the_completed_topic_count():
    assert build_dna(twin(), completed_topics=10).financial_knowledge == "Advanced"


def test_every_band_is_one_of_the_documented_labels():
    dna = build_dna(twin(goals=[GoalIn(name="g", target_amount=100, current_amount=50)]))
    bands = {
        dna.saving_discipline, dna.emergency_readiness, dna.debt_management,
        dna.goal_discipline, dna.budget_stability,
    }
    assert bands <= {"Strong", "Moderate", "Weak"}
    assert dna.financial_knowledge in {"Beginner", "Intermediate", "Advanced"}
