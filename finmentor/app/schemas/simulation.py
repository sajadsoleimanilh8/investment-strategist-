"""What-if / Time Machine / Decision simulator contracts.

Scenario params are produced by app.ai.intent (parser) OR sent directly by an
API client. The engine only ever consumes the structured form below.
"""
from __future__ import annotations

from pydantic import BaseModel


class WhatIfParams(BaseModel):
    monthly_savings_delta: float = 0
    income_pct_delta: float = 0            # 0.2 => +20%
    expense_pct_delta: float = 0
    expense_category_delta: dict[str, float] = {}
    one_time_purchase: float = 0
    horizon_months: int = 24
    goal_id: int | None = None


class ScenarioComparison(BaseModel):
    label: str
    monthly_savings: float
    projected_savings_end: float
    goal_completion_pct: float | None = None
    estimated_goal_date: str | None = None
    emergency_months: float
    health_score: float


class SimulationOut(BaseModel):
    current: ScenarioComparison
    scenario: ScenarioComparison
    deltas: dict[str, float]
    disclaimer: str = (
        "Illustrative projection based on the assumptions you entered. "
        "Not a guarantee of future results."
    )


class DecisionOut(BaseModel):
    purchase_price: float
    savings_before: float
    savings_after: float
    emergency_months_before: float
    emergency_months_after: float
    health_score_before: float
    health_score_after: float
    affordable: bool
    disclaimer: str = "Consequences shown from your numbers. The decision is yours."
