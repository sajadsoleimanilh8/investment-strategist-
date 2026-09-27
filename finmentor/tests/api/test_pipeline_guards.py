"""The pipeline is the security boundary, not the route in front of it.

`POST /api/ai/ask` had a per-user rate limit (a FastAPI dependency) and a
length cap (a Pydantic field). The Telegram bot reaches the same model through
the same `ask_pipeline.answer_question`, in-process, and had neither: one
Telegram account could drive unlimited model calls and unlimited transcript
growth.

That is what "one shared pipeline, two delivery surfaces" costs when the
guards are attached to a surface. Both now go through `ask_pipeline.guard`,
and these tests drive the two surfaces through the same table of cases so the
protections cannot drift apart again.
"""
from __future__ import annotations

import pytest

from app.api import ask as ask_pipeline
from app.core.config import settings
from app.schemas.ai import MAX_QUESTION_LENGTH

TOO_LONG = "x" * (MAX_QUESTION_LENGTH + 1)


@pytest.fixture
def user_id(db) -> int:
    from app.repositories import users as users_repo

    user = users_repo.create(db, telegram_id=900_001)
    db.commit()
    return user.id


# --- the pipeline itself -------------------------------------------------

def test_the_pipeline_refuses_an_oversized_question(db, user_id):
    with pytest.raises(ask_pipeline.QuestionTooLong):
        ask_pipeline.answer_question(db, user_id, TOO_LONG)


def test_the_pipeline_refuses_an_empty_question(db, user_id):
    with pytest.raises(ask_pipeline.QuestionTooLong):
        ask_pipeline.answer_question(db, user_id, "   ")


def test_a_refused_question_writes_no_transcript(db, user_id):
    """Refusing after the write would still pay the storage cost."""
    from app.models.simulation import ChatSession

    with pytest.raises(ask_pipeline.AskRefused):
        ask_pipeline.answer_question(db, user_id, TOO_LONG)

    assert db.query(ChatSession).count() == 0


@pytest.fixture
def budget(monkeypatch):
    """A counting stand-in for the limiter, with no Redis in the picture.

    `test_rate_limit.py` covers whether Redis counts correctly, and skips
    without it because the `ask` bucket fails open by design. The question
    *here* is different and does not need a counter store: does every path to
    the model consult the limiter at all? The bot did not, and that is what
    these assert.
    """
    from app.core import limits

    calls: list[tuple[str, str]] = []
    allowance = {"remaining": 1}

    def counting_allow(bucket: str, identity: str, per_minute: int) -> bool:
        if per_minute <= 0:
            return True
        calls.append((bucket, identity))
        allowance["remaining"] -= 1
        return allowance["remaining"] >= 0

    monkeypatch.setattr(limits, "allow", counting_allow)
    monkeypatch.setattr(settings, "ask_rate_limit_per_minute", 1)
    return {"calls": calls, "allowance": allowance}


def test_the_pipeline_consults_the_limiter(db, user_id, budget):
    ask_pipeline.answer_question(db, user_id, "how am I doing?")

    assert budget["calls"] == [("ask", str(user_id))]


def test_the_pipeline_refuses_once_the_budget_is_spent(db, user_id, budget):
    ask_pipeline.answer_question(db, user_id, "how am I doing?")

    with pytest.raises(ask_pipeline.AskingTooFast):
        ask_pipeline.answer_question(db, user_id, "how am I doing?")


def test_the_budget_is_keyed_on_the_user(db, user_id, budget):
    """Per user, not per address: a shared connection would otherwise let one
    person's burst throttle everybody behind it."""
    with pytest.raises(ask_pipeline.AskingTooFast):
        ask_pipeline.answer_question(db, user_id, "how am I doing?")
        ask_pipeline.answer_question(db, user_id, "how am I doing?")

    assert {identity for _, identity in budget["calls"]} == {str(user_id)}


# --- both surfaces, same table ------------------------------------------

def _over_http(client, user_id: int, question: str) -> tuple[int, str]:
    response = client.post("/api/ai/ask",
                           json={"user_id": user_id, "question": question})
    body = response.json()
    message = body.get("error", {}).get("message", "") if "error" in body else body.get("text", "")
    return response.status_code, message


def _over_telegram(bot_db, user_id: int, question: str) -> tuple[int, str]:
    """The bot's own entry point, which catches the refusal and renders it."""
    from app.bot.handlers import _ask_payload

    return 200, _ask_payload(user_id, question)


def test_http_refuses_an_oversized_question(client, user_id):
    status, _ = _over_http(client, user_id, TOO_LONG)

    assert status == 422


def test_telegram_refuses_an_oversized_question(bot_db, db, user_id):
    """The surface that had no cap at all.

    A sentence rather than an exception: the bot's job is to say why, and the
    limit itself is not repeated in `app/bot/`.
    """
    _, reply = _over_telegram(bot_db, user_id, TOO_LONG)

    assert "longer than I can read" in reply


def test_http_enforces_the_budget(client, user_id, budget):
    _over_http(client, user_id, "how am I doing?")
    status, message = _over_http(client, user_id, "how am I doing?")

    assert status == 429
    assert "give it a moment" in message.lower()


def test_telegram_enforces_the_same_budget(bot_db, db, user_id, budget):
    """The whole point of the change, in one test.

    Before this the bot had no budget at all: the limiter was a FastAPI
    dependency and the bot never went through FastAPI. Same stub, same
    pipeline, same refusal — rendered as a sentence instead of a status code.
    """
    _over_telegram(bot_db, user_id, "how am I doing?")
    _, reply = _over_telegram(bot_db, user_id, "how am I doing?")

    assert "give it a moment" in reply.lower()


def test_neither_surface_keeps_its_own_copy_of_the_limits():
    """A guard duplicated per surface is a guard that will drift.

    Checked structurally: the two delivery modules must reach the budget
    through the pipeline, not call the limiter themselves.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2]
    for module in ("app/api/routes/ai.py", "app/bot/handlers.py"):
        source = (root / module).read_text(encoding="utf-8")
        assert "limits.allow" not in source, f"{module} counts for itself"
        assert "ask_rate_limit_per_minute" not in source, f"{module} knows the budget"


# --- the transcript stays bounded ---------------------------------------

def test_the_transcript_stops_growing(db, user_id):
    """`append_turn` rewrites the whole JSON document every time, so an
    uncapped transcript costs a little more on every question, forever."""
    from app.repositories import chat as chat_repo

    for index in range(ask_pipeline.MAX_TRANSCRIPT_TURNS + 10):
        chat_repo.append_turn(
            db, user_id, question=f"q{index}", answer="a", intent="chat",
            source="local", max_turns=ask_pipeline.MAX_TRANSCRIPT_TURNS,
        )
    db.commit()

    turns = chat_repo.read_transcript(chat_repo.get_or_create(db, user_id))
    assert len(turns) == ask_pipeline.MAX_TRANSCRIPT_TURNS


def test_the_transcript_drops_the_oldest_first(db, user_id):
    """The recent turns are the ones the conversation depends on."""
    from app.repositories import chat as chat_repo

    for index in range(ask_pipeline.MAX_TRANSCRIPT_TURNS + 5):
        chat_repo.append_turn(
            db, user_id, question=f"q{index}", answer="a", intent="chat",
            source="local", max_turns=ask_pipeline.MAX_TRANSCRIPT_TURNS,
        )
    db.commit()

    turns = chat_repo.read_transcript(chat_repo.get_or_create(db, user_id))
    assert turns[-1]["question"] == f"q{ask_pipeline.MAX_TRANSCRIPT_TURNS + 4}"
    assert turns[0]["question"] == "q5"


def test_asking_through_the_pipeline_caps_the_transcript(db, user_id):
    """The cap has to be wired in at the call site, not only available."""
    from app.repositories import chat as chat_repo

    for index in range(ask_pipeline.MAX_TRANSCRIPT_TURNS + 3):
        ask_pipeline.answer_question(db, user_id, f"question {index}")

    turns = chat_repo.read_transcript(chat_repo.get_or_create(db, user_id))
    assert len(turns) == ask_pipeline.MAX_TRANSCRIPT_TURNS
