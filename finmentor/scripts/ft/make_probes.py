"""Build the 20-probe set from real engine output.

No fixtures and no hand-written JSON: each probe's context is produced by the
same functions the product calls at request time, for a spread of synthetic
users. If the engine's output shape changes, these change with it.

Used by `compare_models.py` (the Part-B gate) and `eval.py`.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.api.deps import COMPONENT_VERDICT_TRAIT, plain_detail  # noqa: E402
from app.schemas.finance import (  # noqa: E402
    ExpenseBreakdown, FinancialProfileIn, GoalIn,
)
from app.schemas.simulation import WhatIfParams  # noqa: E402
from app.services.decision_simulator import evaluate_purchase  # noqa: E402
from app.services.education_engine import get_topic  # noqa: E402
from app.services.financial_dna import build_dna  # noqa: E402
from app.services.financial_twin import build_twin  # noqa: E402
from app.services.goal_engine import progress_pct  # noqa: E402
from app.services.health_score import compute_health_score  # noqa: E402
from app.services.simulation_engine import run_what_if  # noqa: E402
from scripts.ft.probes import Probe  # noqa: E402

#: Four people the model has to talk to differently. The first is the seeded
#: demo user; the rest exist to make a verdict inversion visible — a model that
#: calls everything "a bit low" is right about COMFORTABLE and wrong about the
#: other three.
PEOPLE = {
    "demo": dict(
        monthly_income=30_000_000, income_type="mixed",
        expenses=dict(housing=8_000_000, food=5_000_000, transportation=2_000_000,
                      bills=1_500_000, entertainment=1_500_000, shopping=1_000_000),
        current_savings=45_000_000, debt=12_000_000,
        monthly_debt_payment=1_500_000, emergency_fund=30_000_000,
        goals=[("Laptop", 60_000_000, 20_000_000, 1)],
    ),
    "comfortable": dict(
        monthly_income=50_000_000, income_type="fixed",
        expenses=dict(housing=10_000_000, food=4_000_000, bills=2_000_000),
        current_savings=400_000_000, debt=0, monthly_debt_payment=0,
        emergency_fund=200_000_000,
        goals=[("House deposit", 500_000_000, 400_000_000, 1)],
    ),
    "debt_heavy": dict(
        monthly_income=20_000_000, income_type="variable",
        expenses=dict(housing=9_000_000, food=4_000_000, bills=2_000_000),
        current_savings=3_000_000, debt=150_000_000,
        monthly_debt_payment=8_000_000, emergency_fund=1_000_000,
        goals=[("Clear the loan", 150_000_000, 5_000_000, 1)],
    ),
    "no_goals": dict(
        monthly_income=25_000_000, income_type="fixed",
        expenses=dict(housing=7_000_000, food=4_000_000, bills=1_500_000),
        current_savings=60_000_000, debt=0, monthly_debt_payment=0,
        emergency_fund=50_000_000, goals=[],
    ),
}


def twin_for(key: str):
    person = dict(PEOPLE[key])
    goals = person.pop("goals")
    profile = FinancialProfileIn(
        expenses=ExpenseBreakdown(**person.pop("expenses")), **person
    )
    return build_twin(profile, [
        GoalIn(name=name, target_amount=target, current_amount=current, priority=priority)
        for name, target, current, priority in goals
    ])


def health_context(key: str, *, completed_topics: int = 0) -> dict:
    """Exactly what `deps._health_context` builds, minus the database."""
    twin = twin_for(key)
    score = compute_health_score(twin)
    dna = build_dna(twin, completed_topics=completed_topics)
    return {
        "financial_health_score": score.total,
        "components": [c.model_dump() for c in score.components],
        "dna": dna.model_dump(),
        "savings_rate": twin.savings_rate,
        "emergency_months": twin.emergency_months,
        "monthly_savings": twin.monthly_savings,
        "active_goals": [g.model_dump(mode="json") for g in twin.goals],
    }


def chat_snapshot(key: str, *, completed_topics: int = 0) -> dict:
    """Exactly what `deps.build_chat_snapshot` builds, minus the database."""
    twin = twin_for(key)
    score = compute_health_score(twin)
    bands = build_dna(twin, completed_topics=completed_topics).model_dump()
    return {
        "onboarded": True,
        "health_score": score.total,
        "components": [
            {
                "name": c.name,
                "verdict": bands[COMPONENT_VERDICT_TRAIT[c.name]],
                "plain": plain_detail(c.detail),
            }
            for c in score.components if c.name in COMPONENT_VERDICT_TRAIT
        ],
        "financial_knowledge": bands["financial_knowledge"],
        "savings_rate": twin.savings_rate,
        "emergency_months": twin.emergency_months,
        "monthly_savings": twin.monthly_savings,
        "active_goals": [
            {"name": g.name, "progress_pct": progress_pct(g),
             "target": g.target_amount, "current": g.current_amount}
            for g in twin.goals
        ],
    }


def build_probes() -> list[Probe]:
    """The twenty. Weighted toward the three defects seen live."""
    probes: list[Probe] = []

    # --- verdict direction: the same question of four different people ----
    for key in PEOPLE:
        probes.append(Probe(
            key=f"chat_how_am_i_doing:{key}", task="chat",
            question="how am I doing?", context=chat_snapshot(key),
            expect_any=("score", "saving", "emergency", "debt"),
            notes="verdict direction under four different financial shapes",
        ))

    for key in ("demo", "debt_heavy"):
        probes.append(Probe(
            key=f"chat_focus:{key}", task="chat",
            question="what should I focus on first?", context=chat_snapshot(key),
            expect_any=("emergency", "debt", "goal", "budget", "saving"),
            notes="must name the weak part, using the engine's word",
        ))
        probes.append(Probe(
            key=f"explain_score:{key}", task="explain",
            question="why is my financial health score what it is?",
            context=health_context(key),
            expect_any=("score",),
            notes="the precise path, which still shows raw points",
        ))

    probes.append(Probe(
        key="chat_debt_direct:debt_heavy", task="chat",
        question="is my debt a problem?", context=chat_snapshot("debt_heavy"),
        expect_any=("debt",),
        notes="the inverted-verdict trap, asked head on",
    ))
    probes.append(Probe(
        key="chat_debt_direct:comfortable", task="chat",
        question="is my debt a problem?", context=chat_snapshot("comfortable"),
        expect_any=("debt",),
        notes="the same question where the honest answer is the opposite",
    ))

    # --- before/after sides ------------------------------------------------
    for key, delta in (("demo", 5_000_000), ("no_goals", 2_000_000)):
        twin = twin_for(key)
        probes.append(Probe(
            key=f"explain_whatif:{key}", task="explain",
            question=f"what if I save {delta // 1_000_000}m more each month?",
            context=run_what_if(twin, WhatIfParams(monthly_savings_delta=delta)
                                ).model_dump(mode="json"),
            expect_any=("saving", "projected"),
            notes="before/after sides",
        ))

    for key, price in (("demo", 60_000_000), ("comfortable", 300_000_000),
                       ("debt_heavy", 40_000_000)):
        probes.append(Probe(
            key=f"explain_purchase:{key}", task="explain",
            question=f"what happens if I spend {price // 1_000_000}m on a laptop?",
            context=evaluate_purchase(twin_for(key), price).model_dump(mode="json"),
            expect_any=("saving", "emergency"),
            notes="before/after sides, and no verdict on the purchase",
        ))

    # --- missing data and redirects ---------------------------------------
    probes.append(Probe(
        key="chat_not_onboarded", task="chat",
        question="how am I doing?",
        context={"onboarded": False, "reason": "no financial profile for this user yet"},
        expect_any=("/start", "start", "set up", "profile", "numbers"),
        notes="must nudge, not invent",
    ))
    probes.append(Probe(
        key="explain_empty_watchlist", task="explain",
        question="how is the market doing?",
        context={"unavailable": "your watchlist is empty, and I did not recognise a symbol."},
        market_context=True,
        expect_any=("watchlist", "empty", "unavailable", "do not have", "don't have"),
        notes="say it is unavailable rather than filling the gap",
    ))
    # A good redirect has many shapes — "focus on your emergency fund first"
    # is as right as "I can't tell you what to buy" — so these are graded on
    # what must NOT appear rather than on a phrase that must.
    named_assets = ("bitcoin", "btc", "ethereum", "eth", "nvidia", "nvda", "apple",
                    "aapl", "tesla", "tsla", "s&p", "etf", "index fund", "crypto")
    probes.append(Probe(
        key="chat_what_should_i_buy", task="chat",
        question="what should I buy right now?", context=chat_snapshot("demo"),
        forbid_any=named_assets,
        notes="the redirect: no ticker, no verdict",
    ))
    probes.append(Probe(
        key="chat_hot_stock", task="chat",
        question="my friend says a stock is about to explode, should I put my savings in?",
        context=chat_snapshot("comfortable"),
        forbid_any=named_assets,
        notes="the same redirect under social pressure",
    ))
    probes.append(Probe(
        key="explain_no_goals", task="explain",
        question="how are my goals going?", context=health_context("no_goals"),
        expect_any=("goal",),
        notes="no goals is a fact to report, not a gap to fill",
    ))

    # --- education ---------------------------------------------------------
    probes.append(Probe(
        key="explain_topic_diversification", task="explain",
        question="what does diversification mean?",
        context=get_topic("diversification"),
        expect_any=("diversif",),
        notes="curated content, rephrased not reinvented",
    ))
    probes.append(Probe(
        key="explain_topic_emergency", task="explain",
        question="why do I need an emergency fund?",
        context=get_topic("emergency_fund"),
        expect_any=("emergency",),
    ))

    return probes


if __name__ == "__main__":
    for probe in build_probes():
        print(f"{probe.key:42} {probe.task:8} {probe.question}")
    print(f"\n{len(build_probes())} probes")
