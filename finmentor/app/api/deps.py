"""Shared FastAPI dependencies and the glue that turns DB rows into engine input.

The assembly lives here, in the delivery layer: `app/services` stays free of
persistence (see docs/ARCHITECTURE.md) and the routes stay free of duplicated
loading code.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.ai.intent import ParsedIntent
from app.db.session import get_db  # noqa: F401  re-exported for routes
from app.market import cache as market_cache
from app.models.finance import FinancialProfile
from app.models.user import User
from app.repositories import education as education_repo
from app.repositories import goals as goals_repo
from app.repositories import market as market_repo
from app.repositories import profiles as profiles_repo
from app.repositories import users as users_repo
from app.schemas.finance import FinancialTwinOut
from app.schemas.simulation import WhatIfParams
from app.services import market_engine
from app.services.decision_simulator import evaluate_purchase
from app.services.education_engine import get_topic
from app.services.financial_dna import build_dna
from app.services.financial_twin import build_twin
from app.services.health_score import compute_health_score
from app.services.simulation_engine import run_what_if

DbSession = Annotated[Session, Depends(get_db)]


def load_user(db: Session, user_id: int) -> User:
    user = users_repo.get(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    return user


def load_profile(db: Session, user_id: int) -> FinancialProfile:
    load_user(db, user_id)
    profile = profiles_repo.get_by_user(db, user_id)
    if profile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="no financial profile for this user yet",
        )
    return profile


def load_twin(db: Session, user_id: int, *, period: str | None = None) -> FinancialTwinOut:
    """Profile + this period's expenses + active goals -> the Financial Twin."""
    profile = load_profile(db, user_id)
    return build_twin(
        profiles_repo.to_profile_in(db, profile, period=period),
        [goals_repo.to_goal_in(goal) for goal in goals_repo.list_for_user(db, user_id)],
    )


# --- AI context ---------------------------------------------------------
#
# The AI layer never queries the database or calls the engine: it is handed a
# finished set of verified numbers and turns them into prose. Assembling that
# set is delivery-layer work, so it lives here next to `load_twin`.
#
# Every branch returns a plain dict. When something is missing, the context
# says so under "unavailable" — the model is instructed to repeat that rather
# than fill the gap with a guess.

#: What the assistant can actually do, for an unparsed question.
CAPABILITIES = [
    "explain your financial health score",
    "run a what-if on your savings, income or expenses",
    "evaluate a purchase you are considering",
    "show recent market trends from your watchlist",
    "teach a financial concept",
]


def _twin_or_unavailable(db: Session, user_id: int) -> tuple[FinancialTwinOut | None, dict]:
    """The twin, or the reason there isn't one. Never raises for a missing profile."""
    try:
        return load_twin(db, user_id), {}
    except HTTPException as exc:
        if exc.status_code != status.HTTP_404_NOT_FOUND:
            raise
        return None, {"unavailable": f"{exc.detail} — set up a profile first."}


def _health_context(db: Session, user_id: int) -> dict:
    twin, missing = _twin_or_unavailable(db, user_id)
    if twin is None:
        return missing

    score = compute_health_score(twin)
    dna = build_dna(twin, completed_topics=education_repo.count_completed(db, user_id))
    return {
        "financial_health_score": score.total,
        "components": [component.model_dump() for component in score.components],
        "dna": dna.model_dump(),
        "savings_rate": twin.savings_rate,
        "emergency_months": twin.emergency_months,
        "monthly_savings": twin.monthly_savings,
        "active_goals": [goal.model_dump(mode="json") for goal in twin.goals],
    }


def _what_if_context(db: Session, user_id: int, parsed: ParsedIntent) -> dict:
    twin, missing = _twin_or_unavailable(db, user_id)
    if twin is None:
        return missing
    params = parsed.what_if or WhatIfParams()
    return run_what_if(twin, params).model_dump(mode="json")


def _decision_context(db: Session, user_id: int, parsed: ParsedIntent) -> dict:
    twin, missing = _twin_or_unavailable(db, user_id)
    if twin is None:
        return missing
    if not parsed.purchase_price:
        return {"unavailable": "I could not read a price in that question."}
    return evaluate_purchase(twin, parsed.purchase_price).model_dump(mode="json")


def _education_context(parsed: ParsedIntent) -> dict:
    topic = get_topic(parsed.topic_key) if parsed.topic_key else None
    if topic is None:
        return {"unavailable": "I do not have a lesson on that topic yet."}
    return topic


def _market_context(db: Session, user_id: int, parsed: ParsedIntent) -> dict:
    """The user's watchlist ranking, or a named symbol if the question had one."""
    symbol = _symbol_in(parsed.raw, db)
    if symbol is not None:
        points = market_cache.get_or_fetch(db, symbol)
        return {"asset": market_engine.analyze(symbol, points).model_dump(mode="json")}

    watched = market_repo.list_watchlist(db, user_id)
    if not watched:
        return {"unavailable": "your watchlist is empty, and I did not recognise a symbol."}

    reports = [
        market_engine.analyze(item.symbol, market_cache.get_or_fetch(db, item.symbol))
        for item in watched
    ]
    ranked = market_engine.rank_by_momentum(reports)
    return {"watchlist": [report.model_dump(mode="json") for report in ranked]}


def _symbol_in(question: str, db: Session) -> str | None:
    """A known asset named in the question, by symbol or display name."""
    lowered = (question or "").lower()
    for asset in market_repo.list_active_assets(db):
        name = asset.display_name.lower()
        if asset.symbol.lower() in lowered.split() or (name and name in lowered):
            return asset.symbol
    return None


def build_ai_context(
    db: Session, user_id: int, parsed: ParsedIntent
) -> tuple[dict, bool]:
    """Verified numbers for the question, plus whether this is market context.

    Raises 404 only for a user who does not exist. Anything else missing is
    reported inside the context so the assistant can say so out loud.
    """
    load_user(db, user_id)

    if parsed.intent == "health":
        return _health_context(db, user_id), False
    if parsed.intent == "what_if":
        return _what_if_context(db, user_id, parsed), False
    if parsed.intent == "decision":
        return _decision_context(db, user_id, parsed), False
    if parsed.intent == "education":
        return _education_context(parsed), False
    if parsed.intent == "market":
        return _market_context(db, user_id, parsed), True

    return {"available_help": list(CAPABILITIES)}, False
