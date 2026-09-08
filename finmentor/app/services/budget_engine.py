"""Rule-based budget planner (spec section 18). Deterministic, no AI.

Ported from legacy finance/budget_planner.py. 50/30/20 is presented as a
GUIDELINE the user can override, never as universally correct.
"""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_SPLIT = {"needs": 0.5, "wants": 0.3, "savings": 0.2}


@dataclass
class BudgetPlan:
    income: float
    needs: float
    wants: float
    savings: float
    annual_savings: float
    split: dict[str, float]


def plan_budget(monthly_income: float, split: dict[str, float] | None = None) -> BudgetPlan:
    if monthly_income <= 0:
        raise ValueError("monthly_income must be positive")
    split = split or DEFAULT_SPLIT
    if round(sum(split.values()), 4) != 1.0:
        raise ValueError("budget split must sum to 1.0")
    needs = round(monthly_income * split["needs"], 2)
    wants = round(monthly_income * split["wants"], 2)
    savings = round(monthly_income * split["savings"], 2)
    return BudgetPlan(monthly_income, needs, wants, savings, round(savings * 12, 2), split)


def months_to_goal(monthly_savings: float, goal_amount: float, current: float = 0.0) -> float | None:
    remaining = max(0.0, goal_amount - current)
    return None if monthly_savings <= 0 else round(remaining / monthly_savings, 1)
