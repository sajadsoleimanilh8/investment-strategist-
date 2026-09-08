"""Pydantic I/O contracts for the financial engine. English field names only."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class ExpenseBreakdown(BaseModel):
    housing: float = 0
    food: float = 0
    transportation: float = 0
    education: float = 0
    bills: float = 0
    entertainment: float = 0
    shopping: float = 0
    other: float = 0

    def total(self) -> float:
        return sum(self.model_dump().values())

    def essential_total(self) -> float:
        return self.housing + self.food + self.transportation + self.bills


class FinancialProfileIn(BaseModel):
    monthly_income: float = Field(ge=0)
    income_type: str = "fixed"          # fixed|variable|mixed
    expenses: ExpenseBreakdown = ExpenseBreakdown()
    current_savings: float = Field(default=0, ge=0)
    debt: float = Field(default=0, ge=0)
    monthly_debt_payment: float = Field(default=0, ge=0)
    emergency_fund: float = Field(default=0, ge=0)
    risk_profile: str = "moderate"      # conservative|moderate|aggressive
    # What the user intended to spend per category. None until they set one;
    # it is the baseline for the budget-stability score.
    planned_budget: ExpenseBreakdown | None = None


class GoalIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    target_amount: float = Field(gt=0)
    current_amount: float = Field(default=0, ge=0)
    deadline: date | None = None
    priority: int = Field(default=3, ge=1, le=5)   # 1 = highest


class GoalCreate(GoalIn):
    """POST /api/goals — a goal plus the user it belongs to."""

    user_id: int = Field(gt=0)


class GoalOut(GoalIn):
    """A stored goal, with the deterministic goal-engine figures attached."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool = True
    progress_pct: float = 0.0
    estimated_completion: date | None = None


class FinancialTwinOut(BaseModel):
    income: float
    expenses: ExpenseBreakdown = ExpenseBreakdown()
    planned_budget: ExpenseBreakdown | None = None
    monthly_expenses: float
    essential_monthly_expenses: float
    monthly_savings: float
    current_savings: float
    debt: float
    monthly_debt_payment: float
    emergency_fund: float
    savings_rate: float
    emergency_months: float
    goals: list[GoalIn] = []
    risk_profile: str
