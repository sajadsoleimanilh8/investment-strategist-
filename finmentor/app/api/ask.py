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
from app.ai.local_llm import LocalLLMUnavailable
from app.ai.safety import FINANCE_DISCLAIMER
from app.api.deps import CAPABILITIES, build_ai_context, build_chat_snapshot, load_user
from app.core import limits
from app.core.config import settings
from app.repositories import chat as chat_repo
from app.schemas.ai import MAX_QUESTION_LENGTH, AskResponse

class AskRefused(Exception):
    """The question will not be answered, and the caller should say why.

    Carries an HTTP status because both surfaces need to distinguish "too
    long" from "too often", and one of them speaks HTTP. The bot ignores the
    number and shows `message`.
    """

    status_code = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class QuestionTooLong(AskRefused):
    status_code = 422


class AskingTooFast(AskRefused):
    status_code = 429


#: How many exchanges a transcript keeps.
#:
#: `append_turn` reads the whole JSON document, appends one turn and rewrites
#: it, so an uncapped transcript costs a little more on every question forever
#: — and `GET /ai/transcript` returns all of it in one body. The prompt only
#: ever sees the last few turns (`ai_chat_history_turns`), so nothing the
#: assistant does depends on the rest; this is about the row, not the reply.
MAX_TRANSCRIPT_TURNS = 100


def guard(db, user_id: int, question: str) -> str:
    """Everything that must be true before a question costs anything.

    In the pipeline rather than on the route, which is the whole point. The
    HTTP route had a length cap and a per-user budget; the Telegram bot called
    this same function and had neither, so one Telegram account could drive
    unlimited model calls and unlimited transcript growth. Both surfaces now
    pass through here because there is no longer a way to reach the model that
    does not.

    Returns the cleaned question so a caller cannot accidentally use the raw
    one.
    """
    cleaned = (question or "").strip()
    if not cleaned:
        raise QuestionTooLong("Ask me something and I will have a go.")
    if len(cleaned) > MAX_QUESTION_LENGTH:
        raise QuestionTooLong(
            f"That question is longer than I can read ({len(cleaned)} characters; "
            f"the limit is {MAX_QUESTION_LENGTH}). Try the short version."
        )
    if not limits.allow("ask", str(user_id), settings.ask_rate_limit_per_minute):
        raise AskingTooFast(
            "You are asking faster than I can think — give it a moment."
        )
    return cleaned


#: The floor when there is no model at all. A message the parser could not read
#: normally goes to the guide (see `_chat_answer`); this is what the user gets
#: when even that is impossible, because a plain list of what the bot can do
#: beats silence.
CAPABILITY_ANSWER = (
    "I could not tell what you are asking. I can "
    + ", ".join(CAPABILITIES[:-1])
    + f", or {CAPABILITIES[-1]}."
    + f"\n\n⚠️ {FINANCE_DISCLAIMER}"
)


def answer_question(db: Session, user_id: int, question: str) -> AskResponse:
    """Answer one question and record the exchange. Commits.

    Raises 404 only for a user who does not exist, and `AskRefused` for a
    question that is too long or too frequent. Anything else missing is
    reported inside the answer, because "I do not have that" is a better reply
    than an error the user cannot act on.
    """
    load_user(db, user_id)
    question = guard(db, user_id, question)
    parsed = intent_parser.parse(question)

    if parsed.unparsed:
        answer = _chat_answer(db, user_id, question)
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
        intent="chat" if parsed.unparsed else parsed.intent, source=answer.source,
        max_turns=MAX_TRANSCRIPT_TURNS,
    )
    db.commit()
    return answer


def _chat_answer(db: Session, user_id: int, question: str) -> AskResponse:
    """A message that is not a precise question — so answer it as a person would.

    This is the only path with history, and the only one whose context is a
    snapshot rather than the result of one engine call. It is still the engine's
    numbers: the guide is handed figures that were computed before it was asked
    anything, and its reply goes through the same safety layer as every other
    answer.
    """
    snapshot = build_chat_snapshot(db, user_id)
    history = chat_repo.read_transcript(chat_repo.get_or_create(db, user_id))

    try:
        result = synthesizer.chat(question, snapshot, history)
    except LocalLLMUnavailable:
        # No model, no conversation. The canned list is the honest floor.
        return AskResponse(
            text=CAPABILITY_ANSWER,
            source="deterministic",
            used_context={"available_help": list(CAPABILITIES)},
            disclaimer_applied=True,
        )

    return AskResponse(
        text=result["text"],
        source=result["source"],
        used_context=snapshot,
        disclaimer_applied=result["disclaimer_applied"],
    )


def transcript(db: Session, user_id: int) -> list[dict]:
    """The user's saved exchanges, oldest first."""
    load_user(db, user_id)
    return chat_repo.read_transcript(chat_repo.get_or_create(db, user_id))
