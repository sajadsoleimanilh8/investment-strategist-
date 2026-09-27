"""The Financial Twin (spec section 5): a deterministic snapshot object.

Recomputed whenever profile / expenses / goals change. NEVER produced by an LLM.

`derive_figures` is the single definition of the twin's derived arithmetic.
`build_twin` uses it for a stored profile and `simulation_engine.apply_scenario`
uses it for a hypothetical one, so a scenario twin can never drift from a real
one.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.schemas.finance import ExpenseBreakdown, FinancialProfileIn, FinancialTwinOut, GoalIn


@dataclass(frozen=True)
class DerivedFigures:
    """Everything the twin computes rather than stores."""

    monthly_expenses: float
    essential_monthly_expenses: float
    monthly_savings: float
    savings_rate: float
    emergency_months: float


def derive_figures(
    *,
    income: float,
    expenses: ExpenseBreakdown,
    monthly_debt_payment: float,
    emergency_fund: float,
    extra_monthly_savings: float = 0.0,
) -> DerivedFigures:
    """The twin's arithmetic, in one place.

    `extra_monthly_savings` is the what-if "save X more each month" lever: it
    raises monthly savings (and therefore the savings rate) without pretending
    income or expenses changed.
    """
    monthly_expenses = expenses.total()
    essential = expenses.essential_total()
    monthly_savings = income - monthly_expenses - monthly_debt_payment + extra_monthly_savings
    return DerivedFigures(
        monthly_expenses=monthly_expenses,
        essential_monthly_expenses=essential,
        monthly_savings=monthly_savings,
        savings_rate=round(monthly_savings / income, 4) if income else 0.0,
        emergency_months=round(emergency_fund / essential, 2) if essential else 0.0,
    )


def build_twin(profile: FinancialProfileIn, goals: list[GoalIn] | None = None) -> FinancialTwinOut:
    goals = goals or []
    figures = derive_figures(
        income=profile.monthly_income,
        expenses=profile.expenses,
        monthly_debt_payment=profile.monthly_debt_payment,
        emergency_fund=profile.emergency_fund,
    )
    return FinancialTwinOut(
        income=profile.monthly_income,
        income_type=profile.income_type,
        expenses=profile.expenses,
        planned_budget=profile.planned_budget,
        monthly_expenses=figures.monthly_expenses,
        essential_monthly_expenses=figures.essential_monthly_expenses,
        monthly_savings=figures.monthly_savings,
        current_savings=profile.current_savings,
        debt=profile.debt,
        monthly_debt_payment=profile.monthly_debt_payment,
        emergency_fund=profile.emergency_fund,
        savings_rate=figures.savings_rate,
        emergency_months=figures.emergency_months,
        goals=goals,
        risk_profile=profile.risk_profile,
    )
