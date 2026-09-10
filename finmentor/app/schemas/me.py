"""The dashboard's one-shot payload.

Everything here is a re-export of an existing contract — `FinancialTwinOut`,
`HealthScoreOut`, `GoalOut` and the rest are the same objects the older routes
return. Composing rather than redefining them means the web client and the bot
cannot drift onto different shapes of the same number.
"""
from __future__ import annotations

from pydantic import BaseModel

from app.schemas.finance import FinancialTwinOut, GoalOut
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
