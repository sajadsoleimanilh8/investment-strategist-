"""What-if simulator (spec section 8) + shared projection primitives used by
time_machine and decision_simulator. 100% deterministic. The LLM only
explains the returned numbers.

Modelling assumptions, stated once here because every simulator inherits them:

- Projections are straight-line. No interest, no inflation, no market return —
  savings accumulate at the scenario's monthly rate and nothing else happens.
- The whole monthly saving is assumed to flow into the goal being tracked. A
  user splitting money across goals will beat or miss this date; it is an
  illustration of one rate, not a plan.
- A one-time purchase is paid down a waterfall: cash savings first, then the
  emergency fund, then straight into the red. A purchase covered by cash leaves
  the safety net alone; one that outruns cash visibly eats the buffer, which is
  what makes emergency months — and the health score — move.
- `planned_budget` survives income and savings levers, but an expense lever
  clears it. A scenario that spends differently is a proposed new plan, not a
  month where the user lapsed, so it must not be charged a deviation penalty
  against the plan it is replacing.
- Savings may go negative. That is a signal worth showing, not an error.
"""
from __future__ import annotations

from app.schemas.finance import ExpenseBreakdown, FinancialTwinOut, GoalIn
from app.schemas.simulation import ScenarioComparison, SimulationOut, WhatIfParams
from app.services import goal_engine
from app.services.financial_twin import derive_figures
from app.services.health_score import compute_health_score


def apply_scenario(twin: FinancialTwinOut, params: WhatIfParams) -> FinancialTwinOut:
    """Return a NEW twin with the scenario deltas applied.

    Levers, applied in this order: income %, expense % (then per-category
    absolute deltas, floored at zero), the "save X more" delta, and a one-time
    purchase drawn down cash-then-emergency-fund. The input twin is never
    mutated.
    """
    income = twin.income * (1 + params.income_pct_delta)

    scaled = {
        category: max(
            0.0,
            amount * (1 + params.expense_pct_delta)
            + params.expense_category_delta.get(category, 0.0),
        )
        for category, amount in twin.expenses.model_dump().items()
    }
    expenses = ExpenseBreakdown(**scaled)
    current_savings, emergency_fund = _pay_for(
        params.one_time_purchase, twin.current_savings, twin.emergency_fund
    )

    figures = derive_figures(
        income=income,
        expenses=expenses,
        monthly_debt_payment=twin.monthly_debt_payment,
        emergency_fund=emergency_fund,
        extra_monthly_savings=params.monthly_savings_delta,
    )

    return twin.model_copy(
        update={
            "income": income,
            "expenses": expenses,
            "planned_budget": None if _changes_spending(params) else twin.planned_budget,
            "monthly_expenses": figures.monthly_expenses,
            "essential_monthly_expenses": figures.essential_monthly_expenses,
            "monthly_savings": figures.monthly_savings,
            "savings_rate": figures.savings_rate,
            "emergency_months": figures.emergency_months,
            "current_savings": current_savings,
            "emergency_fund": emergency_fund,
        },
        deep=True,
    )


def _changes_spending(params: WhatIfParams) -> bool:
    """Does this scenario propose a different spending plan?"""
    return bool(params.expense_pct_delta) or bool(params.expense_category_delta)


def _pay_for(
    purchase: float, current_savings: float, emergency_fund: float
) -> tuple[float, float]:
    """Draw a purchase down the waterfall: cash, then the fund, then the red.

    Returns the new (current_savings, emergency_fund). Cash already in deficit
    contributes nothing, so the whole purchase falls to the fund and then
    deepens the deficit — a user who is already short does not get to spend
    money they do not have without it showing.
    """
    if purchase <= 0:
        return current_savings, emergency_fund

    paid_from_savings = min(purchase, max(0.0, current_savings))
    shortfall = purchase - paid_from_savings
    paid_from_emergency = min(shortfall, max(0.0, emergency_fund))
    still_short = shortfall - paid_from_emergency

    return (
        current_savings - paid_from_savings - still_short,
        emergency_fund - paid_from_emergency,
    )


def primary_goal(twin: FinancialTwinOut) -> GoalIn | None:
    """The goal a projection tracks by default: the highest-priority active one.

    `load_twin` only ever puts active goals on the twin. Ties keep the order the
    repository returned, which is priority then id — the oldest goal wins.
    """
    return min(twin.goals, key=lambda goal: goal.priority, default=None)


def project(
    twin: FinancialTwinOut,
    months: int,
    *,
    goal: GoalIn | None = None,
    label: str = "current",
) -> ScenarioComparison:
    """Straight-line projection of savings / goal completion / emergency months."""
    goal = goal or primary_goal(twin)
    projected_savings_end = twin.current_savings + twin.monthly_savings * months

    goal_completion_pct: float | None = None
    estimated_goal_date: str | None = None
    if goal is not None:
        saved_toward_goal = goal.current_amount + twin.monthly_savings * months
        completion = saved_toward_goal / goal.target_amount * 100
        goal_completion_pct = round(min(100.0, max(0.0, completion)), 1)
        eta = goal_engine.estimated_completion(goal, twin.monthly_savings)
        estimated_goal_date = eta.isoformat() if eta else None

    return ScenarioComparison(
        label=label,
        monthly_savings=round(twin.monthly_savings, 2),
        projected_savings_end=round(projected_savings_end, 2),
        goal_completion_pct=goal_completion_pct,
        estimated_goal_date=estimated_goal_date,
        emergency_months=twin.emergency_months,
        health_score=compute_health_score(twin).total,
    )


#: The figures a what-if reports a before/after delta for.
DELTA_FIELDS = (
    "monthly_savings",
    "projected_savings_end",
    "goal_completion_pct",
    "emergency_months",
    "health_score",
)


def run_what_if(
    twin: FinancialTwinOut, params: WhatIfParams, *, goal: GoalIn | None = None
) -> SimulationOut:
    """Current path vs the scenario path, with the numeric deltas between them.

    A delta is omitted when either side is null — with no goal there is no
    completion percentage to subtract, and inventing a zero would read as
    "no change" rather than "not applicable".
    """
    goal = goal or primary_goal(twin)
    current = project(twin, params.horizon_months, goal=goal, label="current")
    scenario = project(
        apply_scenario(twin, params), params.horizon_months, goal=goal, label="scenario"
    )

    deltas: dict[str, float] = {}
    for field in DELTA_FIELDS:
        before, after = getattr(current, field), getattr(scenario, field)
        if before is not None and after is not None:
            deltas[field] = round(after - before, 2)

    return SimulationOut(current=current, scenario=scenario, deltas=deltas)
