"""The dashboard's one-shot payload.

Everything here is a re-export of an existing contract — `FinancialTwinOut`,
`HealthScoreOut`, `GoalOut` and the rest are the same objects the older routes
return. Composing rather than redefining them means the web client and the bot
cannot drift onto different shapes of the same number.
"""
from __future__ import annotations

from pydantic import BaseModel

from app.schemas.finance import ExpenseBreakdown, FinancialTwinOut, GoalOut
from app.schemas.health import FinancialDNAOut, HealthScoreOut
from app.schemas.market import MARKET_DISCLAIMER, TrendReportOut


class SummaryOut(BaseModel):
    onboarded: bool
    twin: FinancialTwinOut | None = None
    health: HealthScoreOut | None = None
    dna: FinancialDNAOut | None = None
    goals: list[GoalOut] = []
    watchlist: list[TrendReportOut] = []
    topics_completed: int = 0
    #: carried on the payload because it contains market figures, and every
    #: market payload in this API carries it (spec section 16)
    market_disclaimer: str = MARKET_DISCLAIMER


class ExpensePeriodOut(BaseModel):
    """One month of recorded spending."""

    #: `YYYY-MM`.
    period: str
    expenses: ExpenseBreakdown
    total: float
    #: Housing, food, transportation and bills. The denominator the health
    #: score's runway uses, so it is returned rather than left to the client
    #: to re-derive from a category list it would have to keep in step.
    essential_total: float


class ExpenseHistoryOut(BaseModel):
    """Recorded spending per month, oldest first.

    `periods` holds only the months that have records. A month the user never
    filled in is missing rather than zero: zeros would say they spent nothing,
    and what we have is no record. A client drawing a chart should treat a gap
    as a gap.

    There is deliberately no planned-versus-actual comparison here. The
    planned budget is one current value on the profile, not a value per month,
    so holding a month from last year against today's plan would compare a figure
    to a plan that did not exist when it was spent.
    """

    #: The window that was asked for, echoed so a client can tell "no records
    #: in the last 3 months" from "no records at all".
    months: int
    periods: list[ExpensePeriodOut] = []
