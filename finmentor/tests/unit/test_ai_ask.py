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

def test_an_unreadable_question_never_reaches_the_precise_pipeline(
    db, demo_user_id, monkeypatch
):
    """It is a conversation, not a mis-parsed question: `explain` is for a
    context object, and there is no context object here."""
    def explode(*args, **kwargs):                       # pragma: no cover
        raise AssertionError("an unparsed message must not go through explain()")

    monkeypatch.setattr("app.ai.synthesizer.explain", explode)
    answer = answer_question(db, demo_user_id, "what should I invest in?")

    assert answer.source in {"local", "hybrid"}
    assert answer.used_context["onboarded"] is True


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


# --- the conversational path --------------------------------------------
#
# A message the parser cannot read is not a failure any more: it is a
# conversation. The guide gets a snapshot of figures the engine already
# computed plus the recent history, and its reply is held to exactly the same
# grounding rule as a health explanation.

CHATTY = "i want to save for a car"


def test_a_chatty_message_gets_a_warm_reply_from_the_snapshot(db, demo_user_id):
    answer = answer_question(db, demo_user_id, CHATTY)

    assert answer.source in {"local", "hybrid"}
    assert answer.used_context["onboarded"] is True
    assert answer.used_context["health_score"] > 0
    assert answer.disclaimer_applied is True
    assert FINANCE_DISCLAIMER in answer.text


def test_the_snapshot_carries_figures_the_engine_already_computed(db, demo_user_id):
    from app.api.deps import load_twin
    from app.services.health_score import compute_health_score

    expected = compute_health_score(load_twin(db, demo_user_id)).total
    snapshot = answer_question(db, demo_user_id, CHATTY).used_context

    assert snapshot["health_score"] == expected
    assert {c["name"] for c in snapshot["components"]} == {
        "savings_rate", "emergency_fund", "debt_load", "budget_stability", "goal_progress",
    }
    assert snapshot["dna"]["saving_discipline"]
    assert snapshot["active_goals"][0]["progress_pct"] >= 0


def test_the_model_is_handed_the_snapshot_and_the_last_turn(db, demo_user_id, monkeypatch):
    prompts = []

    def capture(self, prompt, system=None):
        prompts.append(prompt)
        return "Nice work so far."

    monkeypatch.setattr(FakeLocalProvider, "generate", capture)

    answer_question(db, demo_user_id, "hi there")
    answer_question(db, demo_user_id, CHATTY)

    second = prompts[-1]
    assert "health_score" in second, "the snapshot must reach the model"
    assert "hi there" in second, "the previous turn must reach the model"
    assert "Nice work so far." in second, "so must what the guide replied"
    assert CHATTY in second


def test_the_first_message_says_so_rather_than_faking_history(db, demo_user_id, monkeypatch):
    from app.ai.synthesizer import NO_HISTORY

    prompts = []
    monkeypatch.setattr(
        FakeLocalProvider, "generate",
        lambda self, prompt, system=None: prompts.append(prompt) or "Hello.",
    )

    answer_question(db, demo_user_id, "hi there")

    assert NO_HISTORY in prompts[0]


def test_history_is_threaded_across_turns(db, demo_user_id):
    answer_question(db, demo_user_id, "hi there")
    answer_question(db, demo_user_id, CHATTY)

    turns = transcript(db, demo_user_id)

    assert [turn["intent"] for turn in turns] == ["chat", "chat"]
    assert turns[0]["question"] == "hi there"


def test_only_the_configured_number_of_turns_is_shown(db, demo_user_id, monkeypatch):
    from app.ai import synthesizer

    monkeypatch.setattr("app.core.config.settings.ai_chat_history_turns", 2)
    history = [{"question": f"q{i}", "answer": f"a{i}"} for i in range(6)]

    rendered = synthesizer.render_history(history)

    assert "q5" in rendered and "q4" in rendered
    assert "q3" not in rendered


def test_a_dead_local_model_falls_back_to_the_capability_answer(db, demo_user_id):
    """The canned list is still the floor — it is just no longer the default."""
    FakeLocalProvider.unavailable = True
    try:
        answer = answer_question(db, demo_user_id, CHATTY)
    finally:
        FakeLocalProvider.unavailable = False

    assert answer.text == CAPABILITY_ANSWER
    assert answer.source == "deterministic"
    assert answer.used_context["available_help"]
    assert answer.disclaimer_applied is True


def test_a_fabricated_number_in_a_chat_reply_is_still_downgraded(
    db, demo_user_id, monkeypatch
):
    """Warmth buys the model no latitude on numbers."""
    monkeypatch.setattr(
        FakeLocalProvider, "generate",
        lambda self, prompt, system=None: "You are doing great — you have saved $99,000,000!",
    )

    answer = answer_question(db, demo_user_id, CHATTY)

    assert "99,000,000" not in answer.text
    assert answer.source == "deterministic"
    assert str(int(answer.used_context["health_score"])) in answer.text


def test_a_chat_reply_that_gives_advice_is_still_scrubbed(db, demo_user_id, monkeypatch):
    monkeypatch.setattr(
        FakeLocalProvider, "generate",
        lambda self, prompt, system=None: "Great start. You should buy Bitcoin with it.",
    )

    answer = answer_question(db, demo_user_id, CHATTY)

    assert "buy Bitcoin" not in answer.text


def test_a_user_with_no_profile_gets_a_nudge_not_a_number(db, client):
    user_id = client.post("/api/users", json={"telegram_id": 840_001}).json()["id"]

    answer = answer_question(db, user_id, CHATTY)

    assert answer.used_context["onboarded"] is False
    assert "health_score" not in answer.used_context
    assert answer.text.strip()


def test_a_reachable_remote_makes_the_chat_reply_hybrid(db, demo_user_id, monkeypatch):
    monkeypatch.setattr(remote_llm, "is_enabled", lambda: True)
    monkeypatch.setattr(remote_llm, "generate", lambda *a, **k: "A second opinion.")

    answer = answer_question(db, demo_user_id, CHATTY)

    assert answer.source == "hybrid"


# --- the precise paths stay stateless -----------------------------------

def test_a_health_question_gets_no_history_and_no_snapshot(db, demo_user_id, monkeypatch):
    """The whole point of the split: a precise answer is reproducible."""
    prompts = []
    monkeypatch.setattr(
        FakeLocalProvider, "generate",
        lambda self, prompt, system=None: prompts.append(prompt) or "Your score is fine.",
    )

    answer_question(db, demo_user_id, "i want to save for a car")     # seed some history
    answer_question(db, demo_user_id, "why is my health score what it is?")

    health_prompt = prompts[-1]
    assert "Recent conversation" not in health_prompt
    assert "i want to save for a car" not in health_prompt
    assert "financial_health_score" in health_prompt


def test_the_same_health_question_twice_uses_the_same_context(db, demo_user_id):
    first = answer_question(db, demo_user_id, "explain my health score")
    second = answer_question(db, demo_user_id, "explain my health score")

    assert first.used_context == second.used_context


def test_a_precise_answer_is_recorded_under_its_own_intent(db, demo_user_id):
    answer_question(db, demo_user_id, CHATTY)
    answer_question(db, demo_user_id, "explain my health score")

    assert [turn["intent"] for turn in transcript(db, demo_user_id)] == ["chat", "health"]

