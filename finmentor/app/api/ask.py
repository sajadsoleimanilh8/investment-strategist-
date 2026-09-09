"""The `/ask` pipeline, in one place.

Both delivery surfaces — the HTTP route and the Telegram bot — ask questions
the same way, so the pipeline lives here rather than inside either one:

    question -> intent.parse -> structured params -> deterministic engine
             -> verified context -> synthesizer (prose only) -> safety -> user

This module owns the database work: reading the context in and writing the
transcript out. That is deliberate. `app/ai` is handed a finished context and
never touches a session or the engine, which is what makes "the LLM computes
nothing" a structural fact rather than a convention (docs/ARCHITECTURE.md).
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.ai import intent as intent_parser
from app.ai import synthesizer
from app.ai.safety import FINANCE_DISCLAIMER
from app.api.deps import CAPABILITIES, build_ai_context, load_user
from app.repositories import chat as chat_repo
from app.schemas.ai import AskResponse

#: A question the parser could not read gets a plain, honest answer — and no
#: model call. Guessing at an unreadable question is how wrong numbers happen.
CAPABILITY_ANSWER = (
    "I could not tell what you are asking. I can "
    + ", ".join(CAPABILITIES[:-1])
    + f", or {CAPABILITIES[-1]}."
    + f"\n\n⚠️ {FINANCE_DISCLAIMER}"
)


def answer_question(db: Session, user_id: int, question: str) -> AskResponse:
    """Answer one question and record the exchange. Commits.

    Raises 404 only for a user who does not exist; anything else missing is
    reported inside the answer, because "I do not have that" is a better reply
    than an error the user cannot act on.
    """
    load_user(db, user_id)
    parsed = intent_parser.parse(question)

    if parsed.unparsed:
        answer = AskResponse(
            text=CAPABILITY_ANSWER,
            source="deterministic",
            used_context={"available_help": list(CAPABILITIES)},
            disclaimer_applied=True,
        )
    else:
        context, market_context = build_ai_context(db, user_id, parsed)
        result = synthesizer.explain(question, context, market_context=market_context)
        answer = AskResponse(
            text=result["text"],
            source=result["source"],
            used_context=result["used_context"],
            disclaimer_applied=result["disclaimer_applied"],
        )

    chat_repo.append_turn(
        db, user_id,
        question=question, answer=answer.text,
        intent=parsed.intent, source=answer.source,
    )
    db.commit()
    return answer


def transcript(db: Session, user_id: int) -> list[dict]:
    """The user's saved exchanges, oldest first."""
    load_user(db, user_id)
    return chat_repo.read_transcript(chat_repo.get_or_create(db, user_id))
