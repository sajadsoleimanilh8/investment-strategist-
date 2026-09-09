"""Decision Simulator (spec section 10): evaluate a real purchase.
Shows consequences (savings, emergency buffer, health score) — never says
"don't". The output carries no verdict string; the caller renders the numbers
and the user decides.
"""
from __future__ import annotations

from app.schemas.finance import FinancialTwinOut
from app.schemas.simulation import DecisionOut, WhatIfParams
from app.services.health_score import compute_health_score
from app.services.simulation_engine import apply_scenario


def evaluate_purchase(twin: FinancialTwinOut, price: float) -> DecisionOut:
    """Before/after figures for spending `price` out of current savings.

    `affordable` means only this: the price fits in cash savings alone
    (spending your last unit exactly still counts). Reaching the emergency fund
    to close the gap is not affordability — it is borrowing from your own
    safety net, and the numbers say so rather than the label.

    It is a solvency check, not advice: a purchase can be "affordable" and
    still gut a goal, which is why the health score and emergency months travel
    with it. Those two move only when the purchase outruns cash and eats into
    the fund; a purchase covered by cash leaves the buffer — and therefore the
    score — untouched, which is the correct reading.
    """
    after = apply_scenario(twin, WhatIfParams(one_time_purchase=price))
    return DecisionOut(
        purchase_price=price,
        savings_before=twin.current_savings,
        savings_after=after.current_savings,
        emergency_months_before=twin.emergency_months,
        emergency_months_after=after.emergency_months,
        health_score_before=compute_health_score(twin).total,
        health_score_after=compute_health_score(after).total,
        affordable=price <= max(0.0, twin.current_savings),
    )
