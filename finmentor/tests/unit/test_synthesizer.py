"""The three-tier fallback (spec section 15), with a fake local model.

No test here touches a live model: `LOCAL_LLM_PROVIDER=fake` (see conftest)
selects `FakeLocalProvider`, and the remote tier is monkeypatched. The point of
these tests is that an outage degrades the prose while the numbers stay put.
"""
import pytest

from app.ai import remote_llm, synthesizer
from app.ai.local_llm import FakeLocalProvider, LocalLLMUnavailable
from app.ai.safety import FINANCE_DISCLAIMER
from app.schemas.market import MARKET_DISCLAIMER

CONTEXT = {
    "financial_health_score": 62.3,
    "savings_rate": 0.35,
    "monthly_savings": 10_500_000.0,
}


@pytest.fixture
def local_down(monkeypatch):
    """Knock the local model over for one test."""
    monkeypatch.setattr(FakeLocalProvider, "unavailable", True)


@pytest.fixture
def remote_up(monkeypatch):
    """A working remote tier, without a network call."""
    monkeypatch.setattr(remote_llm, "is_enabled", lambda: True)
    monkeypatch.setattr(
        remote_llm, "generate",
        lambda prompt: "Remote draft: your score is 62.3 and savings are steady.",
    )


# --- tier 2: local only (the default) -----------------------------------

def test_local_only_is_the_default_tier():
    result = synthesizer.explain("how am I doing?", CONTEXT)

    assert result["source"] == "local"
    assert result["used_context"] == CONTEXT
    assert result["disclaimer_applied"] is True
    assert FINANCE_DISCLAIMER in result["text"]


def test_the_context_actually_reaches_the_model():
    """The fake echoes context figures, so this proves the handoff."""
    result = synthesizer.explain("how am I doing?", CONTEXT)

    assert "financial_health_score is 62.3" in result["text"]


def test_every_result_carries_a_safety_report():
    result = synthesizer.explain("how am I doing?", CONTEXT)

    assert set(result["safety_report"]) == {
        "buy_sell_scrubbed", "ungrounded_numbers", "disclaimer_added", "downgraded",
    }


# --- tier 1: hybrid -----------------------------------------------------

def test_an_enabled_remote_produces_a_hybrid_answer(remote_up):
    result = synthesizer.explain("how am I doing?", CONTEXT)

    assert result["source"] == "hybrid"
    assert "Merging both drafts" in result["text"]      # the fake merged them
    assert FINANCE_DISCLAIMER in result["text"]


def test_a_remote_that_returns_nothing_falls_back_to_local(monkeypatch):
    monkeypatch.setattr(remote_llm, "is_enabled", lambda: True)
    monkeypatch.setattr(remote_llm, "generate", lambda prompt: None)

    assert synthesizer.explain("how am I doing?", CONTEXT)["source"] == "local"


def test_a_disabled_remote_is_never_called(monkeypatch):
    calls = []
    monkeypatch.setattr(remote_llm, "is_enabled", lambda: False)
    monkeypatch.setattr(remote_llm, "generate", lambda prompt: calls.append(prompt))

    synthesizer.explain("how am I doing?", CONTEXT)

    assert calls == []


def test_the_local_model_dying_mid_merge_keeps_the_remote_draft(monkeypatch, remote_up):
    """First call succeeds (the draft), the merge call fails."""
    calls = {"n": 0}

    def flaky(self, prompt, system=None):
        calls["n"] += 1
        if calls["n"] > 1:
            raise LocalLLMUnavailable("died during merge")
        return "Local draft: score 62.3."

    monkeypatch.setattr(FakeLocalProvider, "generate", flaky)
    result = synthesizer.explain("how am I doing?", CONTEXT)

    assert result["source"] == "hybrid"
    assert "Remote draft" in result["text"]


# --- tier 3: deterministic ----------------------------------------------

def test_a_dead_local_model_serves_the_verified_context(local_down):
    result = synthesizer.explain("how am I doing?", CONTEXT)

    assert result["source"] == "deterministic"
    assert "62.3" in result["text"]                    # the numbers still ship
    assert "10,500,000" in result["text"]
    assert FINANCE_DISCLAIMER in result["text"]
    assert result["used_context"] == CONTEXT


def test_a_dead_local_model_does_not_dump_raw_json(local_down):
    text = synthesizer.explain("how am I doing?", CONTEXT)["text"]

    assert "{" not in text and '"financial_health_score"' not in text
    assert "Financial health score: 62.3" in text


def test_a_dead_local_model_never_raises(local_down):
    # the product must not break because a model is down
    assert synthesizer.explain("anything", {})["source"] == "deterministic"


# --- unavailable data ---------------------------------------------------

def test_an_unavailable_context_is_stated_not_guessed():
    context = {"unavailable": "no financial profile for this user yet."}
    result = synthesizer.explain("how am I doing?", context)

    assert "do not have that information" in result["text"]
    assert "no financial profile" in result["text"]
    assert result["used_context"] == context


def test_an_unavailable_context_still_gets_a_disclaimer():
    result = synthesizer.explain("how am I doing?", {"unavailable": "no data."})
    assert FINANCE_DISCLAIMER in result["text"]


# --- safety is on every path --------------------------------------------

def test_a_model_that_invents_a_number_is_downgraded(monkeypatch):
    monkeypatch.setattr(
        FakeLocalProvider, "generate",
        lambda self, prompt, system=None: "Your score will hit 91.7 next year.",
    )
    result = synthesizer.explain("how am I doing?", CONTEXT)

    assert result["source"] == "deterministic"          # downgraded, not shipped
    assert result["safety_report"]["downgraded"] is True
    assert "91.7" not in result["text"]


def test_a_model_that_gives_trade_advice_is_scrubbed(monkeypatch):
    monkeypatch.setattr(
        FakeLocalProvider, "generate",
        lambda self, prompt, system=None: "Your score is 62.3. You should buy Bitcoin.",
    )
    result = synthesizer.explain("how am I doing?", CONTEXT)

    assert result["safety_report"]["buy_sell_scrubbed"] is True
    assert "buy Bitcoin" not in result["text"]
    assert "62.3" in result["text"]


def test_market_context_switches_the_disclaimer():
    result = synthesizer.explain("how is BTC?", {"change_7d_pct": 4.37},
                                 market_context=True)

    assert MARKET_DISCLAIMER in result["text"]
    assert FINANCE_DISCLAIMER not in result["text"]


@pytest.mark.parametrize("market_context", [False, True])
def test_the_numbers_are_identical_across_tiers(monkeypatch, market_context):
    """A tier change alters the prose, never the figures."""
    local = synthesizer.explain("q", CONTEXT, market_context=market_context)

    monkeypatch.setattr(FakeLocalProvider, "unavailable", True)
    deterministic = synthesizer.explain("q", CONTEXT, market_context=market_context)

    assert local["used_context"] == deterministic["used_context"] == CONTEXT
    assert "62.3" in local["text"] and "62.3" in deterministic["text"]
