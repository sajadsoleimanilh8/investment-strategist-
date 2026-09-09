"""POST /api/ai/ask — the full rule, end to end, with the model faked.

What each test really checks is that `used_context` carries figures the
deterministic engine produced, because that is what makes the answer
trustworthy regardless of what the model said.
"""
import pytest

from app.ai import remote_llm
from app.ai.local_llm import FakeLocalProvider
from app.ai.safety import FINANCE_DISCLAIMER
from app.schemas.market import MARKET_DISCLAIMER
from scripts.seed_demo_user import seed_demo_user
from scripts.seed_market_assets import seed_demo_watchlist, seed_market_assets

PERIOD = "2026-09"


@pytest.fixture
def demo_user_id(client, db, monkeypatch) -> int:
    monkeypatch.setattr("app.repositories.profiles.current_period", lambda *a, **k: PERIOD)
    return seed_demo_user(db, period=PERIOD)


@pytest.fixture
def bare_user_id(client) -> int:
    """A user with no financial profile."""
    return client.post("/api/users", json={"telegram_id": 820_002}).json()["id"]


def ask(client, user_id: int, question: str):
    return client.post("/api/ai/ask", json={"user_id": user_id, "question": question})


# --- health -------------------------------------------------------------

def test_a_health_question_answers_from_the_real_score(client, demo_user_id):
    response = ask(client, demo_user_id, "why is my financial health score what it is?")

    assert response.status_code == 200
    body = response.json()
    assert body["source"] in {"local", "hybrid", "deterministic"}
    assert body["used_context"]["financial_health_score"] == 62.3
    assert len(body["used_context"]["components"]) == 5
    assert body["used_context"]["dna"]["saving_discipline"] == "Strong"
    assert body["disclaimer_applied"] is True
    assert FINANCE_DISCLAIMER in body["text"]


def test_the_answer_quotes_the_engine_not_the_model(client, demo_user_id):
    body = ask(client, demo_user_id, "how is my financial health?").json()

    # the fake echoes context figures; the score in the prose is the real one
    assert "62.3" in body["text"]


# --- what-if ------------------------------------------------------------

def test_a_what_if_question_carries_before_and_after(client, demo_user_id):
    body = ask(client, demo_user_id, "what if I save $5M more each month?").json()

    context = body["used_context"]
    assert context["current"]["monthly_savings"] == 10_500_000
    assert context["scenario"]["monthly_savings"] == 15_500_000
    assert context["deltas"]["monthly_savings"] == 5_000_000
    assert context["scenario"]["estimated_goal_date"] < context["current"]["estimated_goal_date"]


def test_an_income_what_if_is_parsed_and_run(client, demo_user_id):
    body = ask(client, demo_user_id, "what if my income goes up 20%?").json()

    assert body["used_context"]["scenario"]["monthly_savings"] == 16_500_000


# --- decision -----------------------------------------------------------

def test_a_purchase_question_returns_consequences_without_a_verdict(client, demo_user_id):
    body = ask(client, demo_user_id, "should I buy a $60M laptop?").json()

    context = body["used_context"]
    assert context["purchase_price"] == 60_000_000
    assert context["savings_after"] == 0
    assert context["emergency_months_after"] < context["emergency_months_before"]
    assert "you should buy" not in body["text"].lower()


# --- education ----------------------------------------------------------

def test_an_education_question_uses_the_curated_topic(client, demo_user_id):
    body = ask(client, demo_user_id, "what does diversification mean?").json()

    assert body["used_context"]["key"] == "diversification"
    assert body["used_context"]["title"] == "Diversification"


# --- market -------------------------------------------------------------

def test_a_market_question_uses_the_market_disclaimer(client, demo_user_id, db):
    seed_market_assets(db)
    seed_demo_watchlist(db, demo_user_id)
    db.commit()

    body = ask(client, demo_user_id, "how is the market trending?").json()

    assert MARKET_DISCLAIMER in body["text"]
    assert FINANCE_DISCLAIMER not in body["text"]
    assert len(body["used_context"]["watchlist"]) == 4


def test_a_named_symbol_is_analysed(client, demo_user_id, db):
    seed_market_assets(db)
    db.commit()

    body = ask(client, demo_user_id, "what is the price of bitcoin?").json()

    assert body["used_context"]["asset"]["symbol"] == "BTC"
    assert body["used_context"]["asset"]["trend"] in {"Upward", "Downward", "Neutral"}


# --- unparsed -----------------------------------------------------------

def test_a_question_it_cannot_read_gets_the_capabilities_answer(client, demo_user_id, monkeypatch):
    calls = []
    monkeypatch.setattr(
        FakeLocalProvider, "generate",
        lambda self, prompt, system=None: calls.append(prompt) or "should never run",
    )

    body = ask(client, demo_user_id, "asdkjhasd qwe").json()

    assert calls == [], "an unreadable question must not reach the model"
    assert body["source"] == "deterministic"
    assert "explain your financial health score" in body["text"]
    assert body["used_context"]["available_help"]
    assert FINANCE_DISCLAIMER in body["text"]


# --- missing data -------------------------------------------------------

def test_a_user_without_a_profile_is_told_so_not_guessed_at(client, bare_user_id):
    body = ask(client, bare_user_id, "how is my financial health?").json()

    assert "unavailable" in body["used_context"]
    assert "profile" in body["used_context"]["unavailable"]
    assert "do not have that information" in body["text"]


def test_an_unknown_user_is_404(client):
    assert ask(client, 9999, "how am I doing?").status_code == 404


@pytest.mark.parametrize("payload", [{}, {"user_id": 1}, {"question": "hi"}])
def test_an_incomplete_request_is_422(client, payload):
    assert client.post("/api/ai/ask", json=payload).status_code == 422


# --- transcript ---------------------------------------------------------

def test_the_exchange_is_written_to_the_transcript(client, demo_user_id):
    ask(client, demo_user_id, "how is my financial health?")

    transcript = client.get(f"/api/ai/transcript/{demo_user_id}").json()
    assert len(transcript) == 1
    assert transcript[0]["question"] == "how is my financial health?"
    assert transcript[0]["intent"] == "health"
    assert transcript[0]["source"] in {"local", "hybrid", "deterministic"}
    assert transcript[0]["ts"]
    assert transcript[0]["answer"]


def test_a_second_question_appends_to_the_same_session(client, demo_user_id, db):
    ask(client, demo_user_id, "how is my financial health?")
    ask(client, demo_user_id, "what if I save $5M more each month?")

    transcript = client.get(f"/api/ai/transcript/{demo_user_id}").json()
    assert [turn["intent"] for turn in transcript] == ["health", "what_if"]

    from app.models.simulation import ChatSession
    from sqlalchemy import func, select

    assert db.scalar(select(func.count()).select_from(ChatSession)) == 1


def test_an_unreadable_question_is_still_recorded(client, demo_user_id):
    ask(client, demo_user_id, "zzzz")

    transcript = client.get(f"/api/ai/transcript/{demo_user_id}").json()
    assert transcript[0]["intent"] == "smalltalk"


def test_the_transcript_of_an_unknown_user_is_404(client):
    assert client.get("/api/ai/transcript/9999").status_code == 404


# --- fallback tiers, through the API ------------------------------------

def test_the_api_still_answers_when_the_model_is_down(client, demo_user_id, monkeypatch):
    monkeypatch.setattr(FakeLocalProvider, "unavailable", True)

    body = ask(client, demo_user_id, "how is my financial health?").json()

    assert body["source"] == "deterministic"
    assert body["used_context"]["financial_health_score"] == 62.3
    assert "62.3" in body["text"]


def test_the_api_reports_a_hybrid_answer_when_remote_is_up(client, demo_user_id, monkeypatch):
    monkeypatch.setattr(remote_llm, "is_enabled", lambda: True)
    monkeypatch.setattr(remote_llm, "generate", lambda prompt: "Remote draft.")

    assert ask(client, demo_user_id, "how is my financial health?").json()["source"] == "hybrid"
