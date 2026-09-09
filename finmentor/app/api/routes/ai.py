"""ai routes (spec section 22): POST /api/ai/ask.

The architectural rule, end to end and in this order:

    question -> intent.parse -> structured params -> deterministic engine
             -> verified context -> synthesizer (prose only) -> safety -> user

The route owns the database work — reading the context in, writing the
transcript out — so `app/ai` stays persistence-free. Nothing here computes a
number; every figure in the response came from `build_ai_context`.
"""
from __future__ import annotations

from fastapi import APIRouter, status

from app.ai import intent as intent_parser
from app.ai import synthesizer
from app.ai.safety import FINANCE_DISCLAIMER
from app.api.deps import CAPABILITIES, DbSession, build_ai_context, load_user
from app.repositories import chat as chat_repo
from app.schemas.ai import AskRequest, AskResponse

router = APIRouter(prefix="/api", tags=["ai"])

#: A question the parser could not read gets a plain, honest answer — and no
#: model call. Guessing at an unreadable question is how wrong numbers happen.
CAPABILITY_ANSWER = (
    "I could not tell what you are asking. I can "
    + ", ".join(CAPABILITIES[:-1])
    + f", or {CAPABILITIES[-1]}."
    + f"\n\n⚠️ {FINANCE_DISCLAIMER}"
)


@router.post("/ai/ask", response_model=AskResponse)
def ask(payload: AskRequest, db: DbSession) -> AskResponse:
    load_user(db, payload.user_id)
    parsed = intent_parser.parse(payload.question)

    if parsed.unparsed:
        answer = AskResponse(
            text=CAPABILITY_ANSWER,
            source="deterministic",
            used_context={"available_help": list(CAPABILITIES)},
            disclaimer_applied=True,
        )
    else:
        context, market_context = build_ai_context(db, payload.user_id, parsed)
        result = synthesizer.explain(
            payload.question, context, market_context=market_context
        )
        answer = AskResponse(
            text=result["text"],
            source=result["source"],
            used_context=result["used_context"],
            disclaimer_applied=result["disclaimer_applied"],
        )

    chat_repo.append_turn(
        db, payload.user_id,
        question=payload.question, answer=answer.text,
        intent=parsed.intent, source=answer.source,
    )
    db.commit()
    return answer


@router.get("/ai/transcript/{user_id}", status_code=status.HTTP_200_OK)
def get_transcript(user_id: int, db: DbSession) -> list[dict]:
    """The user's saved exchanges, oldest first."""
    load_user(db, user_id)
    return chat_repo.read_transcript(chat_repo.get_or_create(db, user_id))
