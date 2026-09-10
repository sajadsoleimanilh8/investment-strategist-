"""`/api/me/*` — the token-scoped aliases the web client uses.

The older routes take `{user_id}` in the path because the bot's pipeline knew
the id before there was a token. A browser does not: it has an access token and
nothing else, and making it read its own id out of `/auth/me` just to build
every subsequent URL is a round trip for no benefit.

These read the id from the token instead. No new engine logic — every figure
comes from the same builders `deps` already exposes.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import (
    CurrentUser, DbSession, load_twin, require_user,
)
from app.market import cache as market_cache
from app.repositories import education as education_repo
from app.repositories import goals as goals_repo
from app.repositories import market as market_repo
from app.repositories import profiles as profiles_repo
from app.schemas.me import SummaryOut
from app.services import market_engine
from app.services.financial_dna import build_dna
from app.services.goal_engine import estimated_completion, progress_pct
from app.services.health_score import compute_health_score

router = APIRouter(prefix="/api/me", tags=["me"],
                   dependencies=[Depends(require_user)])

#: The dashboard shows a handful of each, not everything the user owns.
TOP_GOALS = 3
WATCHLIST_HEAD = 4


@router.get("/summary", response_model=SummaryOut)
def summary(user: CurrentUser, db: DbSession) -> SummaryOut:
    """Everything the dashboard needs, in one request.

    A user who has not onboarded gets `onboarded: false` and no figures rather
    than a 404 — "you have not set this up yet" is a screen, not an error.
    """
    if profiles_repo.get_by_user(db, user.id) is None:
        return SummaryOut(onboarded=False)

    twin = load_twin(db, user.id)
    score = compute_health_score(twin)
    dna = build_dna(twin, completed_topics=education_repo.count_completed(db, user.id))

    goals = sorted(
        goals_repo.list_for_user(db, user.id),
        key=lambda goal: (goal.priority, -progress_pct(goals_repo.to_goal_in(goal))),
    )[:TOP_GOALS]

    watched = market_repo.list_watchlist(db, user.id)[:WATCHLIST_HEAD]
    reports = market_engine.rank_by_momentum([
        market_engine.analyze(item.symbol, market_cache.get_or_fetch(db, item.symbol))
        for item in watched
    ])

    return SummaryOut(
        onboarded=True,
        twin=twin,
        health=score,
        dna=dna,
        goals=[
            _goal_out(goal, twin.monthly_savings) for goal in goals
        ],
        watchlist=reports,
        topics_completed=education_repo.count_completed(db, user.id),
    )


def _goal_out(goal, monthly_savings: float):
    from app.schemas.finance import GoalOut

    goal_in = goals_repo.to_goal_in(goal)
    return GoalOut(
        **goal_in.model_dump(), id=goal.id, is_active=goal.is_active,
        progress_pct=progress_pct(goal_in),
        estimated_completion=estimated_completion(goal_in, monthly_savings),
    )
