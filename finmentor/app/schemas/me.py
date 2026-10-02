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


class IncomeSignalOut(BaseModel):
    """What the recorded income shows about how steady it is.

    An observation, never a correction. `declared` is what the user set and
    stays that way; `suggested` is what the records look like. When they
    differ, `disagrees` is true and the client can offer the change rather
    than making it.
    """

    periods: int
    #: Too few periods to classify. `suggested` is then null and `disagrees`
    #: is false: two months differing is not a pattern.
    insufficient: bool
    mean: float
    low: float
    high: float
    #: Standard deviation over the mean. Null when the mean is zero, because
    #: the ratio is undefined rather than large.
    variation: float | None = None
    #: What the user told us during onboarding.
    declared: str
    #: `fixed`, `variable`, `mixed`, or null when there is not enough to say.
    suggested: str | None = None
    disagrees: bool = False


class IncomePeriodOut(BaseModel):
    period: str
    amount: float


class IncomeHistoryOut(BaseModel):
    """Recorded monthly income, oldest first, with what it adds up to.

    Only months that have a record. A month with no record is absent rather
    than zero: zero income is a claim and no record is not.
    """

    months: int
    periods: list[IncomePeriodOut] = []
    signal: IncomeSignalOut | None = None
