"""Financial Time Machine (spec section 9): compare several named paths
(current / conservative / improved-savings / increased-expense) over a horizon.

Every path is the same deterministic projection as a what-if — only the input
levers differ. See `simulation_engine` for the modelling assumptions.
"""
from __future__ import annotations

from app.schemas.finance import FinancialTwinOut
from app.schemas.simulation import ScenarioComparison, WhatIfParams
from app.services.simulation_engine import apply_scenario, primary_goal, project

#: Order matters — the UI renders these paths side by side in this sequence.
PRESETS: dict[str, dict] = {
    "current": {},
    "conservative": {"income_pct_delta": -0.10, "expense_pct_delta": 0.05},
    "improved_savings": {"monthly_savings_delta": 5_000_000},
    "increased_expense": {"expense_pct_delta": 0.15},
}


def compare_paths(twin: FinancialTwinOut, horizon_months: int = 36) -> list[ScenarioComparison]:
    """One `ScenarioComparison` per preset, always in `PRESETS` order.

    All paths track the same goal, so their completion percentages are
    comparable. "current" is the untouched twin: an empty preset applies no
    lever, so it equals a plain `project(twin, horizon)`.
    """
    goal = primary_goal(twin)
    paths = []
    for label, preset in PRESETS.items():
        path_twin = apply_scenario(twin, WhatIfParams(**preset)) if preset else twin
        paths.append(project(path_twin, horizon_months, goal=goal, label=label))
    return paths
