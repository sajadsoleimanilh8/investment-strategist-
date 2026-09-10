"""The canonical Phase-3 flow, end to end and entirely deterministic:

    "what if I save $5M more each month?"
      -> intent.parse  -> WhatIfParams(monthly_savings_delta=5_000_000)
      -> run_what_if   -> before/after savings, goal completion, goal date

No LLM is involved at any step; the parser turns text into params and the
engine does every calculation.
"""
import time

import pytest

from app.ai.intent import parse
from app.schemas.finance import ExpenseBreakdown, FinancialProfileIn, GoalIn
from app.services.financial_twin import build_twin
from app.services.simulation_engine import run_what_if

QUESTION = "what if I save $5M more each month?"


@pytest.fixture
def demo_twin():
    """Spec section 29: 30M in, 18M out, 45M saved, 1.5M debt payment, laptop goal."""
    return build_twin(
        FinancialProfileIn(
            monthly_income=30_000_000,
            expenses=ExpenseBreakdown(
                housing=8_000_000, food=5_000_000, transportation=2_000_000,
                bills=1_500_000, entertainment=900_000, shopping=600_000,
            ),
            current_savings=45_000_000, debt=10_000_000,
            monthly_debt_payment=1_500_000, emergency_fund=30_000_000,
        ),
        [GoalIn(name="Laptop", target_amount=60_000_000, current_amount=20_000_000,
                priority=1)],
    )


def test_the_question_parses_into_engine_params():
    parsed = parse(QUESTION)

    assert parsed.intent == "what_if"
    assert parsed.unparsed is False
    assert parsed.what_if.monthly_savings_delta == 5_000_000


def test_the_parsed_params_drive_a_full_numeric_answer(demo_twin):
    parsed = parse(QUESTION)
    out = run_what_if(demo_twin, parsed.what_if)

    assert out.current.monthly_savings == 10_500_000
    assert out.scenario.monthly_savings == 15_500_000
    assert out.deltas["monthly_savings"] == 5_000_000
    assert out.scenario.estimated_goal_date < out.current.estimated_goal_date
    assert out.disclaimer


def test_a_short_horizon_shows_the_goal_moving(demo_twin):
    parsed = parse(QUESTION)
    params = parsed.what_if.model_copy(update={"horizon_months": 2})
    out = run_what_if(demo_twin, params)

    # 20M + 2 months: 41M of 60M current vs 51M of 60M in the scenario
    assert out.current.goal_completion_pct == pytest.approx(68.3, abs=0.1)
    assert out.scenario.goal_completion_pct == pytest.approx(85.0, abs=0.1)
    assert out.deltas["goal_completion_pct"] > 0


def test_the_whole_flow_runs_inside_the_one_second_budget(demo_twin):
    started = time.perf_counter()
    out = run_what_if(demo_twin, parse(QUESTION).what_if)
    elapsed_ms = (time.perf_counter() - started) * 1000

    assert out.deltas["monthly_savings"] == 5_000_000
    assert elapsed_ms < 1000, f"the canonical flow took {elapsed_ms:.0f}ms"


def test_the_flow_never_touches_an_llm():
    """Unimport the model clients, run the flow, and check they stayed gone.

    `sys.modules` is put back exactly as it was. Leaving a module unimported
    would let a later import build a *second* copy of the same class, so a test
    patching `FakeLocalProvider` would patch a class the synthesizer never
    instantiates — a failure that looks like a bug in unrelated code.
    """
    import sys

    prefixes = ("app.ai.local", "app.ai.remote")
    removed = {n: sys.modules[n] for n in list(sys.modules) if n.startswith(prefixes)}
    for name in removed:
        del sys.modules[name]

    try:
        parse(QUESTION)
        assert [n for n in sys.modules if n.startswith(prefixes)] == []
    finally:
        sys.modules.update(removed)
