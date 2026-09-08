"""
Rule-based personal budget planner. Deterministic, explainable, and
crucially NOT "investment advice" — it's a generic allocation heuristic
(50/30/20-style), the same category of guidance found in personal-finance
textbooks. The AI layer can narrate this in natural language, but the
numbers themselves come from plain arithmetic here.
"""
from dataclasses import dataclass

from config import settings


@dataclass
class BudgetPlan:
    income: float
    needs: float
    wants: float
    savings: float
    monthly_savings_in_a_year: float
    notes: str


def plan_budget(monthly_income: float, custom_split: dict = None) -> BudgetPlan:
    if monthly_income <= 0:
        raise ValueError("monthly_income must be positive")

    split = custom_split or settings.budget_split
    needs = round(monthly_income * split["needs"], 2)
    wants = round(monthly_income * split["wants"], 2)
    savings = round(monthly_income * split["savings"], 2)

    notes = (
        f"بر اساس قانون {int(split['needs']*100)}/{int(split['wants']*100)}/{int(split['savings']*100)}: "
        f"{int(split['needs']*100)}٪ برای ضروریات (اجاره، خوراک، قبوض)، "
        f"{int(split['wants']*100)}٪ برای هزینه‌های دلخواه، و "
        f"{int(split['savings']*100)}٪ برای پس‌انداز/سرمایه‌گذاری کم‌ریسک و متنوع — نه یک دارایی خاص."
    )

    return BudgetPlan(
        income=monthly_income,
        needs=needs,
        wants=wants,
        savings=savings,
        monthly_savings_in_a_year=round(savings * 12, 2),
        notes=notes,
    )


def plan_budget_for_goal(monthly_income: float, goal_amount: float, custom_split: dict = None) -> dict:
    """Extra helper: given a savings goal (e.g. for a laptop or a trip),
    estimate how many months it takes at the planned savings rate."""
    plan = plan_budget(monthly_income, custom_split)
    months = None if plan.savings <= 0 else round(goal_amount / plan.savings, 1)
    return {"plan": plan, "goal_amount": goal_amount, "estimated_months": months}
