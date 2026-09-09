"""Financial Health Score + Financial DNA contracts."""
from __future__ import annotations

from pydantic import BaseModel


class HealthComponent(BaseModel):
    name: str          # savings_rate | emergency_fund | debt_load | budget_stability | goal_progress
    points: float
    max_points: float = 20.0
    detail: str = ""


class HealthScoreOut(BaseModel):
    total: float
    components: list[HealthComponent]


class FinancialDNAOut(BaseModel):
    saving_discipline: str      # Strong | Moderate | Weak
    emergency_readiness: str
    debt_management: str
    goal_discipline: str
    budget_stability: str
    financial_knowledge: str    # Beginner | Intermediate | Advanced
