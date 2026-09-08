"""The Financial Twin (spec section 5): a deterministic snapshot object.

Recomputed whenever profile / expenses / goals change. NEVER produced by an LLM.
"""
from __future__ import annotations

from app.schemas.finance import FinancialProfileIn, FinancialTwinOut, GoalIn


def build_twin(profile: FinancialProfileIn, goals: list[GoalIn] | None = None) -> FinancialTwinOut:
    goals = goals or []
    monthly_expenses = profile.expenses.total()
    essential = profile.expenses.essential_total()
    monthly_savings = profile.monthly_income - monthly_expenses - profile.monthly_debt_payment
    savings_rate = monthly_savings / profile.monthly_income if profile.monthly_income else 0.0
    emergency_months = profile.emergency_fund / essential if essential else 0.0
    return FinancialTwinOut(
        income=profile.monthly_income,
        expenses=profile.expenses,
        planned_budget=profile.planned_budget,
        monthly_expenses=monthly_expenses,
        essential_monthly_expenses=essential,
        monthly_savings=monthly_savings,
        current_savings=profile.current_savings,
        debt=profile.debt,
        monthly_debt_payment=profile.monthly_debt_payment,
        emergency_fund=profile.emergency_fund,
        savings_rate=round(savings_rate, 4),
        emergency_months=round(emergency_months, 2),
        goals=goals,
        risk_profile=profile.risk_profile,
    )
