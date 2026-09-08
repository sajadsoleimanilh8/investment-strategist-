"""What-if simulator (spec section 8) + shared projection primitives used by
time_machine and decision_simulator. 100% deterministic. The LLM only
explains the returned numbers.
# >>> finmentor-stub <<<
"""
from __future__ import annotations

from app.schemas.finance import FinancialTwinOut
from app.schemas.simulation import ScenarioComparison, SimulationOut, WhatIfParams


def apply_scenario(twin: FinancialTwinOut, params: WhatIfParams) -> FinancialTwinOut:
    """Return a NEW twin with the scenario deltas applied (income %, expense %,
    category deltas, savings delta, one-time purchase)."""
    raise NotImplementedError("phase-3")


def project(twin: FinancialTwinOut, months: int) -> ScenarioComparison:
    """Straight-line projection of savings / goal completion / emergency months."""
    raise NotImplementedError("phase-3")


def run_what_if(twin: FinancialTwinOut, params: WhatIfParams) -> SimulationOut:
    raise NotImplementedError("phase-3: current vs apply_scenario(); compute deltas")
