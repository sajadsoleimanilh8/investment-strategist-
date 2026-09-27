"""ai routes (spec section 22): POST /api/ai/ask.

Thin: the pipeline itself lives in `app.api.ask`, shared with the Telegram
bot so there is exactly one implementation of the architectural rule.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api import ask as ask_pipeline
from app.api.deps import (
    CurrentUser, DbSession, OwnedUserId, assert_owns, require_user,
)
from app.schemas.ai import AskRequest, AskResponse

#: Guarded at the router, not per route: a route added here later is
#: protected by default instead of by remembering.
router = APIRouter(prefix="/api", tags=["ai"],
                   dependencies=[Depends(require_user)])


@router.post("/ai/ask", response_model=AskResponse)
def ask(payload: AskRequest, db: DbSession, current_user: CurrentUser) -> AskResponse:
    """Thin on purpose.

    The per-user budget and the length cap used to be a dependency and a
    schema rule here, which meant the Telegram bot — calling the same pipeline
    in-process — had neither. They moved into `ask_pipeline.guard`, so this
    route's remaining job is to turn the pipeline's refusal into a status
    code. The schema still bounds `question`, which gives a form a field-level
    error; the pipeline bound is what makes the rule true for every caller.
    """
    assert_owns(current_user, payload.user_id)
    try:
        return ask_pipeline.answer_question(db, payload.user_id, payload.question)
    except ask_pipeline.AskRefused as refused:
        raise HTTPException(refused.status_code, refused.message) from refused


@router.get("/ai/transcript/{user_id}", status_code=status.HTTP_200_OK)
def get_transcript(user_id: OwnedUserId, db: DbSession) -> list[dict]:
    return ask_pipeline.transcript(db, user_id)
