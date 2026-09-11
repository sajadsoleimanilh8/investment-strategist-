"""Synthetic people, and the real contexts the engine builds for them.

The fine-tuning set needs variety in the *shape* of someone's finances, not in
their names: a model that has only ever seen a comfortable saver learns to call
everything Strong. So the population is generated across the axes the health
score actually reads — savings rate, emergency cover, debt burden, budget
adherence, goal progress — with the extremes represented on purpose.

Deterministic: same seed, same forty people, so a dataset can be rebuilt and
diffed. Nothing here is a fixture; every context comes back through the same
engine calls the product makes at request time.
"""
from __future__ import annotations

import random
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.api.deps import COMPONENT_VERDICT_TRAIT, plain_detail  # noqa: E402
from app.schemas.finance import (  # noqa: E402
    ExpenseBreakdown, FinancialProfileIn, FinancialTwinOut, GoalIn,
)
from app.services.education_engine import list_topics  # noqa: E402
from app.services.financial_dna import build_dna  # noqa: E402
from app.services.financial_twin import build_twin  # noqa: E402
from app.services.goal_engine import progress_pct  # noqa: E402
from app.services.health_score import compute_health_score  # noqa: E402

SEED = 20260909

#: The buckets the split is stratified over. A model that only ever saw
#: `comfortable` would learn that the answer is always "you're doing well".
BUCKETS = (
    "broke",           # nothing saved, nothing spare
    "debt_heavy",      # income goes to repayments
    "comfortable",     # strong on every axis
    "no_goals",        # healthy, but nothing to aim at
    "overdrawn",       # a purchase would put them under
    "debt_free",       # no debt, thin cover
    "steady",          # unremarkable, the common case
    "not_onboarded",   # no profile at all
)


@dataclass
class Person:
    key: str
    bucket: str
    profile: FinancialProfileIn | None      # None == not onboarded
    goals: list[GoalIn]
    completed_topics: int = 0

    @property
    def onboarded(self) -> bool:
        return self.profile is not None


def _expenses(rng: random.Random, income: float, ratio: float) -> ExpenseBreakdown:
    """Spend `ratio` of income, split over the categories with some jitter."""
    total = income * ratio
    weights = {
        "housing": rng.uniform(0.30, 0.50), "food": rng.uniform(0.15, 0.25),
        "transportation": rng.uniform(0.05, 0.15), "bills": rng.uniform(0.05, 0.12),
        "entertainment": rng.uniform(0.02, 0.10), "shopping": rng.uniform(0.02, 0.10),
    }
    scale = total / sum(weights.values())
    return ExpenseBreakdown(**{k: round(w * scale, -3) for k, w in weights.items()})


def _goal(rng: random.Random, name: str, target: float, progress: float) -> GoalIn:
    return GoalIn(
        name=name, target_amount=round(target, -3),
        current_amount=round(target * progress, -3),
        priority=rng.choice([1, 1, 2, 3, 3, 4, 5]),
    )


GOAL_NAMES = ("Laptop", "Emergency fund", "House deposit", "Car", "Trip",
              "Course fees", "Phone", "Camera", "Bike", "Wedding")


def _make(rng: random.Random, index: int, bucket: str, tag: str = "") -> Person:
    """One person, shaped to land in `bucket` once the engine scores them."""
    income = round(rng.uniform(12_000_000, 60_000_000), -5)

    key = f"p{tag}{index:02d}_{bucket}"
    if bucket == "not_onboarded":
        return Person(key, bucket, None, [])

    if bucket == "broke":
        spend, savings, debt, payment, fund = 0.97, 500_000, 0, 0, 200_000
    elif bucket == "debt_heavy":
        spend, savings, debt = 0.62, income * rng.uniform(0.1, 0.4), income * rng.uniform(5, 9)
        payment, fund = income * rng.uniform(0.30, 0.45), income * rng.uniform(0.05, 0.2)
    elif bucket == "comfortable":
        spend, savings, debt = 0.42, income * rng.uniform(8, 20), 0
        payment, fund = 0, income * rng.uniform(6, 12)
    elif bucket == "overdrawn":
        spend, savings, debt = 0.80, income * rng.uniform(0.05, 0.25), income * rng.uniform(1, 3)
        payment, fund = income * rng.uniform(0.05, 0.12), income * rng.uniform(0.02, 0.1)
    elif bucket == "debt_free":
        spend, savings, debt = 0.70, income * rng.uniform(1, 3), 0
        payment, fund = 0, income * rng.uniform(0.5, 1.5)
    else:                                   # steady, no_goals
        spend, savings, debt = rng.uniform(0.60, 0.75), income * rng.uniform(2, 6), \
            income * rng.uniform(0.5, 2)
        payment, fund = income * rng.uniform(0.04, 0.12), income * rng.uniform(1.5, 4)

    #: Roughly half the population has set a planned budget; the other half
    #: scores neutral on stability, which is a different sentence to write.
    expenses = _expenses(rng, income, spend)
    planned = None
    if rng.random() < 0.5:
        drift = rng.uniform(0.9, 1.25)
        planned = ExpenseBreakdown(**{
            k: round(v * drift, -3) for k, v in expenses.model_dump().items() if v
        })

    profile = FinancialProfileIn(
        monthly_income=income, income_type=rng.choice(["fixed", "variable", "mixed"]),
        expenses=expenses, current_savings=round(savings, -3), debt=round(debt, -3),
        monthly_debt_payment=round(payment, -3), emergency_fund=round(fund, -3),
        risk_profile=rng.choice(["conservative", "moderate", "aggressive"]),
        planned_budget=planned,
    )

    goals: list[GoalIn] = []
    if bucket != "no_goals":
        for _ in range(rng.choice([1, 1, 2, 2, 3])):
            goals.append(_goal(
                rng, rng.choice(GOAL_NAMES), income * rng.uniform(1, 15),
                rng.choice([0.0, 0.05, 0.2, 0.33, 0.5, 0.68, 0.9]),
            ))

    return Person(key, bucket, profile, goals,
                  completed_topics=rng.choice([0, 0, 1, 3, 5, 9]))


def build_population(count: int = 40, seed: int = SEED, tag: str = "") -> list[Person]:
    """`count` people, cycling the buckets so every shape is represented.

    `tag` goes into the key. Without it two populations drawn from different
    seeds produce the same key sequence — `p00_broke`, `p01_debt_heavy`, … —
    and a held-out slice cannot prove it is held out, because its overlap check
    compares labels that collide by construction rather than the people behind
    them.
    """
    rng = random.Random(seed)
    return [_make(rng, i, BUCKETS[i % len(BUCKETS)], tag) for i in range(count)]


# --- the real contexts ---------------------------------------------------
#
# These mirror `deps._health_context` and `deps.build_chat_snapshot` exactly.
# They are duplicated rather than imported because those two take a `Session`,
# and the training set must not need a database — but the shape is the
# product's, and `tests/unit/test_ft_dataset.py` asserts they stay in step.

def twin_for(person: Person) -> FinancialTwinOut:
    return build_twin(person.profile, person.goals)


def health_context(person: Person) -> dict:
    twin = twin_for(person)
    score = compute_health_score(twin)
    dna = build_dna(twin, completed_topics=person.completed_topics)
    return {
        "financial_health_score": score.total,
        "components": [c.model_dump() for c in score.components],
        "dna": dna.model_dump(),
        "savings_rate": twin.savings_rate,
        "emergency_months": twin.emergency_months,
        "monthly_savings": twin.monthly_savings,
        "active_goals": [g.model_dump(mode="json") for g in twin.goals],
    }


def chat_snapshot(person: Person) -> dict:
    if not person.onboarded:
        return {"onboarded": False,
                "reason": "no financial profile for this user yet — set up a profile first."}

    twin = twin_for(person)
    score = compute_health_score(twin)
    bands = build_dna(twin, completed_topics=person.completed_topics).model_dump()
    return {
        "onboarded": True,
        "health_score": score.total,
        "components": [
            {"name": c.name, "verdict": bands[COMPONENT_VERDICT_TRAIT[c.name]],
             "plain": plain_detail(c.detail)}
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


TOPIC_KEYS = tuple(topic["key"] for topic in list_topics())


if __name__ == "__main__":
    import collections

    people = build_population()
    print(collections.Counter(p.bucket for p in people))
    for person in people[:6]:
        if not person.onboarded:
            print(f"{person.key:22} not onboarded")
            continue
        snap = chat_snapshot(person)
        verdicts = " ".join(f"{c['name'][:4]}={c['verdict'][:4]}" for c in snap["components"])
        print(f"{person.key:22} score={snap['health_score']:5.1f}  {verdicts}")
