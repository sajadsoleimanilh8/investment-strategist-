"""Decision Simulator (spec section 10): evaluate a real purchase.
Shows consequences (emergency buffer, health score) — never says "don't".
# >>> finmentor-stub <<<
"""
from __future__ import annotations

from app.schemas.finance import FinancialTwinOut
from app.schemas.simulation import DecisionOut


def evaluate_purchase(twin: FinancialTwinOut, price: float) -> DecisionOut:
    raise NotImplementedError("phase-3")
