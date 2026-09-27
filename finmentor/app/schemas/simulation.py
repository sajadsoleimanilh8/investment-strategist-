"""What-if / Time Machine / Decision simulator contracts.

Scenario params are produced by app.ai.intent (parser) OR sent directly by an
API client. The engine only ever consumes the structured form below.
"""
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

from app.schemas.finance import FINITE, MONEY_CEILING

#: The longest projection the engine will draw. Fifty years is already past
#: the point where a straight-line model says anything useful; the reason for
#: a ceiling at all is arithmetic. `horizon_months` is an `int`, and Python
#: ints are arbitrary precision, so an unbounded one reaches
#: `monthly_savings * months` and raises `OverflowError: int too large to
#: convert to float` — an unhandled 500 from a value a client chose.
MAX_HORIZON_MONTHS = 600

#: A percentage lever, as a fraction: 0.2 is +20%. The floor is -1 because
#: that is income or spending falling to exactly zero, and there is no
#: meaning below it. The ceiling allows a hundredfold increase, which is far
#: past any scenario worth modelling and still finite.
PCT_DELTA = Field(default=0.0, ge=-1, le=100)

#: An absolute money lever. Signed, unlike the money fields in `finance.py`:
#: "save two million less each month" is a real scenario.
SIGNED_MONEY = Field(default=0.0, ge=-MONEY_CEILING, le=MONEY_CEILING)


class WhatIfParams(BaseModel):
    """The scenario levers.

    Bounded for the same reason the profile is (see `app/schemas/finance.py`):
    these values are multiplied by a horizon and fed to the health score, so
    an infinity or an unbounded integer here is an infinity in somebody's
    projection. With every lever bounded and the horizon capped, the largest
    figure the engine can produce is finite and representable, which is what
    makes `allow_inf_nan=False` on the output models below a backstop rather
    than a live failure mode.
    """

    model_config = FINITE

    monthly_savings_delta: float = SIGNED_MONEY
    income_pct_delta: float = PCT_DELTA            # 0.2 => +20%
    expense_pct_delta: float = PCT_DELTA
    expense_category_delta: dict[
        str, Annotated[float, Field(ge=-MONEY_CEILING, le=MONEY_CEILING)]
    ] = {}
    one_time_purchase: float = Field(default=0.0, ge=0, le=MONEY_CEILING)
    horizon_months: int = Field(default=24, ge=1, le=MAX_HORIZON_MONTHS)
    goal_id: int | None = Field(default=None, gt=0)


class ScenarioComparison(BaseModel):
    # A backstop. With every input lever bounded this cannot trigger, and
    # that is the point: if it ever does, something upstream lost a bound,
    # and a loud failure beats `"monthly_savings": null` in a field the
    # web client's types declare as a number.
    model_config = FINITE

    label: str
    monthly_savings: float
    projected_savings_end: float
    goal_completion_pct: float | None = None
    estimated_goal_date: str | None = None
    emergency_months: float
    health_score: float


class SimulationOut(BaseModel):
    model_config = FINITE

    current: ScenarioComparison
    scenario: ScenarioComparison
    deltas: dict[str, float]
    disclaimer: str = (
        "Illustrative projection based on the assumptions you entered. "
        "Not a guarantee of future results."
    )


class DecisionOut(BaseModel):
    model_config = FINITE

    purchase_price: float
    savings_before: float
    savings_after: float
    emergency_months_before: float
    emergency_months_after: float
    health_score_before: float
    health_score_after: float
    affordable: bool
    disclaimer: str = "Consequences shown from your numbers. The decision is yours."
