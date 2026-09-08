"""Financial DNA (spec section 7): human-readable labels from deterministic
metrics. Pure rules; the AI only narrates the result.

Every band comes from the health-score components, so a label can never
disagree with the number next to it. Bands are read as health, not magnitude:
`debt_exposure = "Strong"` means the debt burden is comfortably low.

    Strong    >= 14/20     (70%)
    Moderate  >=  7/20     (35%)
    Weak      <   7/20
"""
from __future__ import annotations

from app.schemas.finance import FinancialTwinOut
from app.schemas.health import FinancialDNAOut
from app.services import health_score

STRONG_POINTS = 14.0
MODERATE_POINTS = 7.0

#: Completed /learn topics needed for each knowledge label (12 topics exist).
INTERMEDIATE_TOPICS = 4
ADVANCED_TOPICS = 9


def _band(value: float, weak_below: float = MODERATE_POINTS,
          strong_above: float = STRONG_POINTS) -> str:
    if value < weak_below:
        return "Weak"
    if value >= strong_above:
        return "Strong"
    return "Moderate"


def knowledge_level(completed_topics: int) -> str:
    """Observable rule: how many of the 12 `/learn` topics the user finished.

    Sourced from `education_progress` (see `repositories.education`). A user
    who has completed nothing is a Beginner — which is also what a brand-new
    account looks like, and that is the honest label for it.
    """
    if completed_topics >= ADVANCED_TOPICS:
        return "Advanced"
    if completed_topics >= INTERMEDIATE_TOPICS:
        return "Intermediate"
    return "Beginner"


def build_dna(twin: FinancialTwinOut, completed_topics: int = 0) -> FinancialDNAOut:
    return FinancialDNAOut(
        saving_discipline=_band(health_score.score_savings_rate(twin.savings_rate)),
        emergency_readiness=_band(health_score.score_emergency_fund(twin.emergency_months)),
        debt_exposure=_band(
            health_score.score_debt_load(twin.monthly_debt_payment, twin.income)
        ),
        goal_discipline=_band(health_score.score_goal_progress(twin.goals)),
        budget_stability=_band(
            health_score.score_budget_stability(twin.planned_budget, twin.expenses)
        ),
        financial_knowledge=knowledge_level(completed_topics),
    )
