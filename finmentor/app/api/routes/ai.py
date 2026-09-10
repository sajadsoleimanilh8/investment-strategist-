"""ai routes (spec section 22): POST /api/ai/ask.

Thin: the pipeline itself lives in `app.api.ask`, shared with the Telegram
bot so there is exactly one implementation of the architectural rule.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api import ask as ask_pipeline
from app.api.deps import (
    CurrentUser, DbSession, OwnedUserId, ask_rate_limit, assert_owns, require_user,
)
from app.schemas.ai import AskRequest, AskResponse

#: Guarded at the router, not per route: a route added here later is
#: protected by default instead of by remembering.
router = APIRouter(prefix="/api", tags=["ai"],
                   dependencies=[Depends(require_user)])


@router.post("/ai/ask", response_model=AskResponse,
             dependencies=[Depends(ask_rate_limit)])
def ask(payload: AskRequest, db: DbSession, current_user: CurrentUser) -> AskResponse:
    """The one route that costs a model call, so the one route with a per-user
    budget. The limit is on the caller in the token, not on their address —
    two people behind one router are two budgets."""
    assert_owns(current_user, payload.user_id)
    return ask_pipeline.answer_question(db, payload.user_id, payload.question)


@router.get("/ai/transcript/{user_id}", status_code=status.HTTP_200_OK)
def get_transcript(user_id: OwnedUserId, db: DbSession) -> list[dict]:
    return ask_pipeline.transcript(db, user_id)
