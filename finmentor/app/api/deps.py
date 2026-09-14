"""Shared FastAPI dependencies and the glue that turns DB rows into engine input.

The assembly lives here, in the delivery layer: `app/services` stays free of
persistence (see docs/ARCHITECTURE.md) and the routes stay free of duplicated
loading code.
"""
from __future__ import annotations

import re
import logging
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.ai.intent import ParsedIntent
from app.core import security
from app.core.config import settings
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
from app.services.goal_engine import progress_pct as goal_progress_pct
from app.services.financial_twin import build_twin
from app.services.health_score import compute_health_score
from app.services.simulation_engine import run_what_if

log = logging.getLogger("finmentor.api")

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


#: Which DNA trait describes which health component. The engine already
#: decided whether each part of someone's finances is Strong, Moderate or Weak;
#: this is the wiring that lets the chat snapshot carry that word next to the
#: thing it describes, instead of in a separate dict.
#:
#: A 3B given "debt_load: 17.5 out of 20" reads "17.5 is a lot of debt". Given
#: "debt_load, Strong" it has nothing left to get wrong. Judging a bounded
#: score is exactly the reasoning small models fail at, and it is reasoning the
#: engine has already done — so the chat snapshot does not ask for it.
COMPONENT_VERDICT_TRAIT = {
    "savings_rate": "saving_discipline",
    "emergency_fund": "emergency_readiness",
    "debt_load": "debt_management",
    "budget_stability": "budget_stability",
    "goal_progress": "goal_discipline",
}

#: A score note inside a detail string — "(20 pts at 25%)". Prose only in the
#: chat snapshot: a raw scoring rule is one more number to misread.
_SCORE_NOTE = re.compile(r"\s*\((?:[^()]*\bpts?\b[^()]*)\)")
_NEUTRAL_NOTE = re.compile(r"\s*,?\s*so this scores neutral\s*$")


def plain_detail(detail: str) -> str:
    """A component's detail with its scoring arithmetic stripped out."""
    cleaned = _NEUTRAL_NOTE.sub("", _SCORE_NOTE.sub("", detail or ""))
    return cleaned.strip()


def build_chat_snapshot(db: Session, user_id: int) -> dict:
    """Where this person stands, for the free-chat path — and nothing more.

    The guide is handed figures the engine has already computed, never rows to
    do arithmetic on — and, since the engine also decided what those figures
    mean, each component arrives with its verdict attached. The model's job is
    to copy a word and write warmly around it, not to grade anyone.

    Deliberately narrower than `_health_context`: no points, no maximums, no
    scale. Those stay on the precise `/health` path, which shows them in a bar
    chart the user can read for themselves.
    """
    twin, missing = _twin_or_unavailable(db, user_id)
    if twin is None:
        return {"onboarded": False, "reason": missing.get("unavailable", "")}

    score = compute_health_score(twin)
    dna = build_dna(twin, completed_topics=education_repo.count_completed(db, user_id))
    bands = dna.model_dump()

    return {
        "onboarded": True,
        "health_score": score.total,
        "components": [
            {
                "name": component.name,
                "verdict": bands[COMPONENT_VERDICT_TRAIT[component.name]],
                "plain": plain_detail(component.detail),
            }
            for component in score.components
            if component.name in COMPONENT_VERDICT_TRAIT
        ],
        "financial_knowledge": bands["financial_knowledge"],
        "savings_rate": twin.savings_rate,
        "emergency_months": twin.emergency_months,
        "monthly_savings": twin.monthly_savings,
        "active_goals": [
            {
                "name": goal.name,
                "progress_pct": goal_progress_pct(goal),
                "target": goal.target_amount,
                "current": goal.current_amount,
            }
            for goal in twin.goals
        ],
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


# --- web authentication --------------------------------------------------
#
# The bot never comes through here: it resolves a user from the Telegram update
# and calls the pipeline functions directly. These dependencies exist for the
# browser client, and guarding a route cannot break the bot.

def require_user(
    db: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    """The user behind a valid access token, or 401.

    `WWW-Authenticate` is set so a client can tell "you are not logged in"
    from "you are logged in and not allowed", which is the difference between
    showing a login form and showing an error.
    """
    try:
        token = security.bearer_token(authorization)
        user_id = security.decode_token(token, expect=security.ACCESS)
    except security.TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = users_repo.get(db, user_id)
    if user is None:                      # deleted while a valid token was live
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="token is not valid",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


CurrentUser = Annotated[User, Depends(require_user)]


def owned_user_id(user_id: int, current_user: CurrentUser) -> int:
    """A path `{user_id}` the caller is actually allowed to read or write.

    403, not 404: the caller is authenticated and this is a real resource they
    may not touch. Pretending it does not exist would be a lie the client
    cannot act on.
    """
    if user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="you can only access your own data",
        )
    return user_id


OwnedUserId = Annotated[int, Depends(owned_user_id)]


# --- rate limiting -------------------------------------------------------
#
# Redis is optional infrastructure. If it is down, the limiter logs and lets the
# request through: a cache outage taking the whole API with it would be a worse
# failure than the one the limiter prevents.

def _allow(bucket: str, identity: str, per_minute: int) -> bool:
    if per_minute <= 0:
        return True
    try:
        import redis

        client = redis.Redis.from_url(settings.redis_url, socket_timeout=0.25)
        key = security.rate_limit_key(identity, bucket)
        used = client.incr(key)
        if used == 1:
            client.expire(key, 60)
        return used <= per_minute
    except Exception as exc:                       # unreachable, missing, misconfigured
        log.warning("rate limiter unavailable, allowing the request: %s", exc)
        return True


def auth_rate_limit(request: Request) -> None:
    """Per-IP, on signup and login — the endpoints worth guessing against."""
    client = request.client.host if request.client else "unknown"
    if not _allow("auth", client, settings.auth_rate_limit_per_minute):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too many attempts — wait a minute and try again",
        )


def ask_rate_limit(current_user: CurrentUser) -> None:
    """Per-user, on /ai/ask — the one route that costs a model call.

    Per *user* rather than per address on purpose: a shared connection would
    otherwise let one person's burst throttle everyone behind it.
    """
    if not _allow("ask", str(current_user.id), settings.ask_rate_limit_per_minute):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="you are asking faster than I can think — give it a moment",
        )


def simulation_rate_limit(current_user: CurrentUser) -> None:
    """Per-user, on /simulations.

    Cheaper than a model call — no network, a few hundred microseconds of
    arithmetic — but it writes a row per request, so an unbounded loop fills a
    table rather than a queue. The same budget as /ask is generous for a person
    and still bounds the damage.
    """
    if not _allow("simulation", str(current_user.id), settings.ask_rate_limit_per_minute):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="that is a lot of simulations at once — give it a moment",
        )


def assert_owns(current_user: User, user_id: int) -> int:
    """The body-payload counterpart to `owned_user_id`.

    Some routes carry the user id in the request body rather than the path
    (`POST /goals`, `POST /simulations`, `POST /ai/ask`). A path dependency
    cannot reach those, so the handler calls this instead — same 403, same
    reasoning.
    """
    if user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="you can only access your own data",
        )
    return user_id
