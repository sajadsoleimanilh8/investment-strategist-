"""Pydantic I/O contracts for the financial engine. English field names only.

Two rules every money field here obeys, both of them about what must never
reach the engine rather than about what a person might plausibly type.

**No infinities, no NaN.** Python's `json.loads` accepts the non-standard
`Infinity` and `NaN` literals, and Pydantic's float validator lets them
through by default — `inf >= 0` is true, so `Field(ge=0)` is no defence. An
infinite income reaches `derive_figures`, `inf - inf` produces NaN, and the
NaN is written to a `double precision` column where it poisons every later
read of that account. `MONEY` and `allow_inf_nan=False` close that off at the
edge, which is the only place it can be closed once.

**A ceiling as well as a floor.** `MONEY_CEILING` is not a judgement about
anybody's salary; it is the point past which float arithmetic stops being
worth trusting and a projection over 600 months can still be represented
exactly. It sits far above any real figure in this product's currency.
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, ConfigDict, Field

#: Well above any real figure, well below the range where multiplying by a
#: 600-month horizon loses precision.
MONEY_CEILING = 1e12

#: The shape every money field takes: finite, not negative, bounded.
MONEY = Field(default=0.0, ge=0, le=MONEY_CEILING)

#: Rejects `Infinity`, `-Infinity` and `NaN` on every field of the model.
FINITE = ConfigDict(allow_inf_nan=False)


class ExpenseBreakdown(BaseModel):
    """One month's spending per category.

    Bounded like every other money field. Nothing in the product produces a
    negative category total: `apply_scenario` already floors each scaled
    category at zero before constructing one of these, so `ge=0` refuses
    input nobody legitimately sends rather than narrowing a real case.
    """

    model_config = FINITE

    housing: float = MONEY
    food: float = MONEY
    transportation: float = MONEY
    education: float = MONEY
    bills: float = MONEY
    entertainment: float = MONEY
    shopping: float = MONEY
    other: float = MONEY

    def total(self) -> float:
        return sum(self.model_dump().values())

    def essential_total(self) -> float:
        return self.housing + self.food + self.transportation + self.bills


class FinancialProfileIn(BaseModel):
    model_config = FINITE

    monthly_income: float = Field(ge=0, le=MONEY_CEILING)
    income_type: str = "fixed"          # fixed|variable|mixed
    expenses: ExpenseBreakdown = ExpenseBreakdown()
    current_savings: float = MONEY
    debt: float = MONEY
    monthly_debt_payment: float = MONEY
    emergency_fund: float = MONEY
    risk_profile: str = "moderate"      # conservative|moderate|aggressive
    # What the user intended to spend per category. None until they set one;
    # it is the baseline for the budget-stability score.
    planned_budget: ExpenseBreakdown | None = None


class GoalIn(BaseModel):
    model_config = FINITE

    name: str = Field(min_length=1, max_length=120)
    target_amount: float = Field(gt=0, le=MONEY_CEILING)
    current_amount: float = Field(default=0, ge=0, le=MONEY_CEILING)
    deadline: date | None = None
    priority: int = Field(default=3, ge=1, le=5)   # 1 = highest


class GoalUpdate(GoalIn):
    """PUT /api/goals/{goal_id} — a replace, plus the archive switch.

    `is_active` is optional rather than defaulted so that omitting it leaves
    the goal's current state alone. The web client declared this field long
    before the API honoured it, which made the TypeScript a promise nothing
    kept: a caller could send `is_active: false` and watch the goal stay in
    the list.
    """

    is_active: bool | None = None


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
    #: Carried so a client can send back what it was given. Without it the
    #: profile form had nothing to seed from and defaulted to "fixed", which
    #: silently reset the field on every save — see `Profile.tsx`.
    income_type: str = "fixed"
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
