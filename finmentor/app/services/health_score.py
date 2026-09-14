"""Financial Health Score (spec section 6). 5 components x 20 points = 0..100.

Single source of truth for the scoring formula. The AI may EXPLAIN a score
but must never compute or fabricate one, and no route may assemble a partial
score of its own — call `compute_health_score` and render what it returns.

Component formulas (all clamped to 0..20, rounded to 0.1):

| Component        | 0 points          | 20 points               |
|------------------|-------------------|-------------------------|
| savings_rate     | rate <= 0         | rate >= 25%             |
| emergency_fund   | 0 months          | >= 6 months of essentials |
| debt_load        | payments >= 40% of income | no debt payments |
| budget_stability | >= 50% deviation from plan | <= 5% deviation  |
| goal_progress    | nothing saved toward goals | every active goal funded |

Two components have a neutral score for "the user has not given us this yet":
no planned budget and no active goals both score 12/20 rather than 0. Scoring
them zero would punish someone for a question they were never asked; scoring
them full marks would reward it. Having goals and neglecting them still
scores 0.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from app.schemas.finance import ExpenseBreakdown, FinancialTwinOut, GoalIn
from app.schemas.health import HealthComponent, HealthScoreOut
from app.services.goal_engine import progress_pct

MAX_COMPONENT_POINTS = 20.0

#: Spending within this share of the plan counts as fully stable.
STABILITY_TOLERANCE = 0.05
#: Deviation at or beyond this share of the plan scores zero.
STABILITY_CEILING = 0.50
#: Score used when the user has not set a planned budget yet — neither
#: rewarded nor punished for a baseline they were never asked for.
STABILITY_NEUTRAL_POINTS = 12.0
#: Same reasoning for a user who has not created any goal yet.
GOAL_NEUTRAL_POINTS = 12.0


def _clamp(x: float, lo: float = 0.0, hi: float = MAX_COMPONENT_POINTS) -> float:
    return max(lo, min(hi, x))


def _as_mapping(value: Mapping[str, float] | ExpenseBreakdown | None) -> dict[str, float]:
    if value is None:
        return {}
    if isinstance(value, ExpenseBreakdown):
        return value.model_dump()
    return dict(value)


def score_savings_rate(rate: float) -> float:
    # 0% -> 0 pts, >=25% -> 20 pts, linear in between.
    return round(_clamp(rate / 0.25 * 20), 1)


def score_emergency_fund(emergency_months: float) -> float:
    # 0 months -> 0, >=6 months -> 20.
    return round(_clamp(emergency_months / 6 * 20), 1)


def score_debt_load(monthly_debt_payment: float, monthly_income: float) -> float:
    # debt-to-income: <=0 -> 20, >=40% -> 0.
    if monthly_income <= 0:
        return 0.0
    dti = monthly_debt_payment / monthly_income
    return round(_clamp((1 - dti / 0.40) * 20), 1)


def budget_deviation(
    planned: Mapping[str, float] | ExpenseBreakdown | None,
    actual: Mapping[str, float] | ExpenseBreakdown | None,
) -> float | None:
    """Total absolute per-category miss, as a share of the planned total.

    Over- and under-spending both count: swapping 1M of food for 1M of
    shopping is a real deviation from the plan even though the total matches.
    Returns None when there is no plan to compare against.
    """
    planned_map = _as_mapping(planned)
    actual_map = _as_mapping(actual)
    planned_total = sum(planned_map.values())
    if planned_total <= 0:
        return None
    gap = sum(
        abs(actual_map.get(category, 0.0) - planned_map.get(category, 0.0))
        for category in set(planned_map) | set(actual_map)
    )
    return gap / planned_total


def score_budget_stability(
    planned: Mapping[str, float] | ExpenseBreakdown | None,
    actual: Mapping[str, float] | ExpenseBreakdown | None,
) -> float:
    """How closely the month's spending tracked the plan.

    Deviation <= 5% scores 20, >= 50% scores 0, linear in between. Without a
    planned budget the score is the documented neutral 12/20.
    """
    deviation = budget_deviation(planned, actual)
    if deviation is None:
        return STABILITY_NEUTRAL_POINTS
    if deviation <= STABILITY_TOLERANCE:
        return MAX_COMPONENT_POINTS
    span = STABILITY_CEILING - STABILITY_TOLERANCE
    return round(_clamp((1 - (deviation - STABILITY_TOLERANCE) / span) * 20), 1)


def score_goal_progress(goals: Sequence[GoalIn]) -> float:
    """Priority-weighted mean progress across the user's active goals.

    Priority 1 (highest) weighs 5x, priority 5 weighs 1x. The caller passes
    active goals only — `repositories.goals.list_for_user` filters them.

    With no goals at all there is nothing to measure, so the score is the
    documented neutral `GOAL_NEUTRAL_POINTS` — the same treatment as a missing
    planned budget. A user who *has* goals and has saved nothing toward them
    still scores 0: that is a measured result, not a missing input.
    """
    if not goals:
        return GOAL_NEUTRAL_POINTS
    weights = [6 - goal.priority for goal in goals]
    total_weight = sum(weights)
    if total_weight <= 0:
        return 0.0
    weighted = sum(progress_pct(goal) / 100 * weight for goal, weight in zip(goals, weights))
    return round(_clamp(weighted / total_weight * 20), 1)


def compute_health_score(twin: FinancialTwinOut) -> HealthScoreOut:
    """The whole score, from the deterministic twin. No I/O, no AI."""
    savings = score_savings_rate(twin.savings_rate)
    emergency = score_emergency_fund(twin.emergency_months)
    debt = score_debt_load(twin.monthly_debt_payment, twin.income)
    stability = score_budget_stability(twin.planned_budget, twin.expenses)
    goals = score_goal_progress(twin.goals)

    deviation = budget_deviation(twin.planned_budget, twin.expenses)
    components = [
        HealthComponent(
            name="savings_rate",
            points=savings,
            detail=f"{twin.savings_rate * 100:.1f}% of income saved (20 pts at 25%)",
        ),
        HealthComponent(
            name="emergency_fund",
            points=emergency,
            detail=f"{twin.emergency_months:.1f} months of essential expenses (20 pts at 6)",
        ),
        HealthComponent(
            name="debt_load",
            points=debt,
            detail=(
                f"debt payments are {twin.monthly_debt_payment / twin.income * 100:.1f}% of income"
                if twin.income > 0
                else "no income recorded"
            ),
        ),
        HealthComponent(
            name="budget_stability",
            points=stability,
            detail=(
                "no planned budget set yet, so this scores neutral"
                if deviation is None
                else f"spending deviated {deviation * 100:.1f}% from the plan"
            ),
        ),
        HealthComponent(
            name="goal_progress",
            points=goals,
            detail=(
                f"{len(twin.goals)} active goal(s), priority-weighted"
                if twin.goals
                else "no active goals — add one to start tracking progress here"
            ),
        ),
    ]
    return HealthScoreOut(
        total=round(sum(component.points for component in components), 1),
        components=components,
    )
