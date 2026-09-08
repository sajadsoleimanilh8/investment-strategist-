"""Financial Time Machine (spec section 9): compare several named paths
(current / conservative / improved-savings / increased-expense) over a horizon.
# >>> finmentor-stub <<<
"""
from __future__ import annotations

from app.schemas.finance import FinancialTwinOut
from app.schemas.simulation import ScenarioComparison

PRESETS = {
    "current": {},
    "conservative": {"income_pct_delta": -0.10, "expense_pct_delta": 0.05},
    "improved_savings": {"monthly_savings_delta": 5_000_000},
    "increased_expense": {"expense_pct_delta": 0.15},
}


def compare_paths(twin: FinancialTwinOut, horizon_months: int = 36) -> list[ScenarioComparison]:
    raise NotImplementedError("phase-3: run each preset through simulation_engine.project")
