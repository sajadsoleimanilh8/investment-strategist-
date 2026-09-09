"""`app.api.ask.answer_question` — the pipeline both delivery surfaces call.

The HTTP route and the Telegram bot are now two callers of one function, so
this is where the contract lives: same shape, same grounding, same persistence,
whichever surface asked.
"""
import pytest

from app.ai import remote_llm
from app.ai.local_llm import FakeLocalProvider
from app.ai.safety import FINANCE_DISCLAIMER
from app.api.ask import CAPABILITY_ANSWER, answer_question, transcript
from app.schemas.ai import AskResponse
from scripts.seed_demo_user import seed_demo_user

PERIOD = "2026-09"


@pytest.fixture
def demo_user_id(db, monkeypatch) -> int:
    monkeypatch.setattr("app.repositories.profiles.current_period", lambda *a, **k: PERIOD)
    return seed_demo_user(db, period=PERIOD)


# --- the shape ----------------------------------------------------------

def test_it_returns_an_askresponse_with_a_grounded_context(db, demo_user_id):
    answer = answer_question(db, demo_user_id, "why is my financial health score what it is?")

    assert isinstance(answer, AskResponse)
    assert answer.source in {"local", "hybrid", "deterministic"}
    assert answer.disclaimer_applied is True
    assert answer.used_context["financial_health_score"] > 0
    assert FINANCE_DISCLAIMER in answer.text


def test_the_numbers_come_from_the_engine_not_the_model(db, demo_user_id):
    from app.api.deps import load_twin
    from app.services.health_score import compute_health_score

    expected = compute_health_score(load_twin(db, demo_user_id)).total
    answer = answer_question(db, demo_user_id, "explain my health score")

    assert answer.used_context["financial_health_score"] == expected


def test_a_what_if_is_run_by_the_engine(db, demo_user_id):
    answer = answer_question(db, demo_user_id, "what if I save 5m more each month?")

    context = answer.used_context
    assert context["scenario"]["monthly_savings"] > context["current"]["monthly_savings"]


def test_a_purchase_question_reports_before_and_after(db, demo_user_id):
    answer = answer_question(db, demo_user_id, "should I buy a 60m laptop?")

    assert answer.used_context["savings_after"] < answer.used_context["savings_before"]


# --- the unparsed path calls no model -----------------------------------

def test_an_unreadable_question_gets_the_capabilities_answer_and_no_model_call(
    db, demo_user_id, monkeypatch
):
    def explode(*args, **kwargs):                       # pragma: no cover
        raise AssertionError("the model must not be called for an unparsed question")

    monkeypatch.setattr("app.ai.synthesizer.explain", explode)
    answer = answer_question(db, demo_user_id, "what should I invest in?")

    assert answer.text == CAPABILITY_ANSWER
    assert answer.source == "deterministic"


# --- the fallback tiers, from this entry point --------------------------

def test_a_dead_local_model_still_answers_with_the_real_figures(db, demo_user_id):
    FakeLocalProvider.unavailable = True
    try:
        answer = answer_question(db, demo_user_id, "explain my health score")
    finally:
        FakeLocalProvider.unavailable = False

    assert answer.source == "deterministic"
    assert answer.used_context["financial_health_score"] > 0
    assert FINANCE_DISCLAIMER in answer.text


def test_a_reachable_remote_produces_a_hybrid_answer(db, demo_user_id, monkeypatch):
    monkeypatch.setattr(remote_llm, "is_enabled", lambda: True)
    monkeypatch.setattr(remote_llm, "generate", lambda *a, **k: "A second opinion.")

    answer = answer_question(db, demo_user_id, "explain my health score")

    assert answer.source == "hybrid"


# --- persistence --------------------------------------------------------

def test_every_exchange_is_written_to_the_transcript(db, demo_user_id):
    answer_question(db, demo_user_id, "explain my health score")
    answer_question(db, demo_user_id, "what if I save 5m more each month?")

    turns = transcript(db, demo_user_id)

    assert len(turns) == 2
    assert turns[0]["intent"] == "health"
    assert turns[1]["intent"] == "what_if"
    assert all(turn["answer"] for turn in turns)


def test_a_user_with_no_history_has_an_empty_transcript(db, demo_user_id):
    assert transcript(db, demo_user_id) == []


def test_an_unknown_user_is_a_404(db):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as raised:
        answer_question(db, 999_999, "explain my health score")
    assert raised.value.status_code == 404


def test_a_user_without_a_profile_is_told_so_rather_than_crashing(db, client):
    user_id = client.post("/api/users", json={"telegram_id": 830_004}).json()["id"]

    answer = answer_question(db, user_id, "explain my health score")

    assert "unavailable" in answer.used_context
    assert answer.text.strip()
