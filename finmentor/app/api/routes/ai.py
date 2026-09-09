"""ai routes (spec section 22): POST /api/ai/ask.

Thin: the pipeline itself lives in `app.api.ask`, shared with the Telegram
bot so there is exactly one implementation of the architectural rule.
"""
from __future__ import annotations

from fastapi import APIRouter, status

from app.api import ask as ask_pipeline
from app.api.deps import DbSession
from app.schemas.ai import AskRequest, AskResponse

router = APIRouter(prefix="/api", tags=["ai"])


@router.post("/ai/ask", response_model=AskResponse)
def ask(payload: AskRequest, db: DbSession) -> AskResponse:
    return ask_pipeline.answer_question(db, payload.user_id, payload.question)


@router.get("/ai/transcript/{user_id}", status_code=status.HTTP_200_OK)
def get_transcript(user_id: int, db: DbSession) -> list[dict]:
    return ask_pipeline.transcript(db, user_id)
