"""The view builders, fed real engine output for the demo user.

These are the strings a person actually reads, so the assertions are about what
must and must not appear: the figures the engine computed, the right
disclaimer, and — in `decision_view` — no verdict of any kind.
"""
import pytest

from app.bot import views
from app.bot.formatting import money
from app.schemas.finance import GoalOut
from app.schemas.market import MARKET_DISCLAIMER, TrendReportOut
from app.schemas.simulation import WhatIfParams
from app.services.budget_engine import plan_budget
from app.services.decision_simulator import evaluate_purchase
from app.services.education_engine import get_topic, list_topics
from app.services.financial_dna import build_dna
from app.services.goal_engine import estimated_completion, progress_pct
from app.services.health_score import compute_health_score
from app.services.simulation_engine import run_what_if
from app.services.time_machine import compare_paths
from app.ai.safety import FINANCE_DISCLAIMER
from scripts.seed_demo_user import seed_demo_user

PERIOD = "2026-09"


@pytest.fixture
def twin(db, monkeypatch):
    from app.api.deps import load_twin

    monkeypatch.setattr("app.repositories.profiles.current_period", lambda *a, **k: PERIOD)
    user_id = seed_demo_user(db, period=PERIOD)
    return load_twin(db, user_id)


@pytest.fixture
def goal_outs(db, twin):
    from app.repositories import goals as goals_repo

    out = []
    for goal in goals_repo.list_for_user(db, 1):
        goal_in = goals_repo.to_goal_in(goal)
        out.append(GoalOut(
            **goal_in.model_dump(), id=goal.id, is_active=goal.is_active,
            progress_pct=progress_pct(goal_in),
            estimated_completion=estimated_completion(goal_in, twin.monthly_savings),
        ))
    return out


# --- health + DNA -------------------------------------------------------

def test_health_view_shows_the_score_and_every_component(db, twin):
    score = compute_health_score(twin)
    dna = build_dna(twin, completed_topics=0)

    text = views.health_view(twin, score, dna)

    assert f"{score.total:.1f}/100" in text
    for component in score.components:
        assert views.COMPONENT_LABELS[component.name] in text
        assert f"{component.points:.1f}/20" in text
    assert FINANCE_DISCLAIMER in text


def test_health_view_carries_the_dna_bands(twin):
    dna = build_dna(twin, completed_topics=0)
    text = views.health_view(twin, compute_health_score(twin), dna)

    assert dna.saving_discipline in text
    assert "Debt management" in text
    assert dna.financial_knowledge in text


def test_dna_view_names_all_six_traits(twin):
    text = views.dna_view(build_dna(twin, completed_topics=0))

    for label in ("Saving discipline", "Emergency readiness", "Debt management",
                  "Goal discipline", "Budget stability", "Financial knowledge"):
        assert label in text


def test_profile_view_shows_the_stored_position(twin):
    text = views.profile_view(twin)

    assert money(twin.income) in text
    assert money(twin.current_savings) in text
    assert money(twin.debt) in text
    assert twin.risk_profile.title() in text


# --- budget -------------------------------------------------------------

def test_budget_view_shows_the_split_and_calls_it_a_guideline(twin):
    plan = plan_budget(twin.income)
    text = views.budget_view(plan)

    assert money(plan.needs) in text
    assert money(plan.wants) in text
    assert money(plan.savings) in text
    assert "guideline, not a rule" in text
    assert FINANCE_DISCLAIMER in text


# --- goals --------------------------------------------------------------

def test_goals_view_shows_progress_and_eta(goal_outs):
    assert goal_outs, "the demo user should have at least one goal"
    text = views.goals_view(goal_outs)

    for goal in goal_outs:
        assert goal.name in text
        assert f"{goal.progress_pct:.1f}%" in text
    assert FINANCE_DISCLAIMER in text


def test_goals_view_with_nothing_to_show_invites_a_goal():
    text = views.goals_view([])

    assert "not set a goal yet" in text


def test_goal_added_view_repeats_the_goal_back(goal_outs):
    text = views.goal_added_view(goal_outs[0])

    assert goal_outs[0].name in text
    assert "Added" in text


# --- simulation ---------------------------------------------------------

def test_simulation_view_has_current_scenario_and_result_blocks(twin):
    result = run_what_if(twin, WhatIfParams(monthly_savings_delta=5_000_000))
    text = views.simulation_view(result)

    assert "CURRENT" in text and "SCENARIO" in text and "RESULT" in text
    assert money(result.current.monthly_savings) in text
    assert money(result.scenario.monthly_savings) in text
    assert "Illustrative projection" in text
    assert FINANCE_DISCLAIMER in text


def test_time_machine_view_lists_every_path(twin):
    paths = compare_paths(twin)
    text = views.time_machine_view(paths)

    for path in paths:
        assert path.label in text
    assert "not forecasts" in text


# --- the decision view carries no verdict -------------------------------

@pytest.mark.parametrize("price", [10_000_000, 60_000_000, 500_000_000])
def test_decision_view_states_consequences_and_never_a_verdict(twin, price):
    decision = evaluate_purchase(twin, price)
    text = views.decision_view(decision).lower()

    assert money(decision.savings_before).lower() in text
    assert money(decision.savings_after).lower() in text
    for verdict in ("should buy", "should not buy", "shouldn't buy", "don't buy",
                    "do not buy", "advisable", "recommend", "good idea", "bad idea",
                    "worth buying", "affordable", "unaffordable"):
        assert verdict not in text, f"decision_view leaked a verdict: {verdict!r}"


def test_decision_view_shows_the_hit_to_the_emergency_fund(twin):
    decision = evaluate_purchase(twin, 60_000_000)
    text = views.decision_view(decision)

    assert f"{decision.emergency_months_before:.1f}" in text
    assert f"{decision.emergency_months_after:.1f}" in text


# --- market -------------------------------------------------------------

def _report(symbol: str, change_7d: float) -> TrendReportOut:
    return TrendReportOut(
        symbol=symbol, latest_price=100.0, change_1d_pct=0.5,
        change_7d_pct=change_7d, change_30d_pct=2.0, moving_average_short=99.0,
        moving_average_long=98.0, volatility=0.02, volatility_label="Low",
        trend="Upward",
    )


def test_market_view_is_ranked_and_disclaimed():
    text = views.market_view([_report("BTC", 4.4), _report("ETH", 1.1)])

    assert text.index("BTC") < text.index("ETH")
    assert "4.40%" in text
    assert MARKET_DISCLAIMER in text
    assert FINANCE_DISCLAIMER not in text


def test_an_empty_watchlist_still_carries_the_market_disclaimer():
    text = views.market_view([])

    assert "watchlist is empty" in text
    assert MARKET_DISCLAIMER in text


# --- education ----------------------------------------------------------

@pytest.mark.parametrize("topic", list_topics(), ids=lambda t: t["key"])
def test_every_topic_renders(topic):
    text = views.topic_view(topic)

    assert topic["title"] in text
    assert topic["explanation"][:40] in text
    assert "Common mistake" in text


def test_quiz_view_asks_the_question_without_giving_the_answer():
    topic = get_topic("diversification")
    text = views.quiz_view(topic)

    assert topic["quiz"]["question"] in text
    assert topic["quiz"]["options"][topic["quiz"]["answer_idx"]] not in text


def test_quiz_result_marks_right_and_wrong():
    topic = get_topic("diversification")
    correct_idx = topic["quiz"]["answer_idx"]

    assert "Correct" in views.quiz_result_view(topic, correct_idx)
    assert "Not quite" in views.quiz_result_view(topic, (correct_idx + 1) % 3)


def test_help_view_lists_every_command():
    text = views.help_view()

    for command in ("/start", "/health", "/budget", "/goals", "/simulate",
                    "/market", "/watchlist", "/learn", "/ask"):
        assert command in text
    assert "never tell you what to buy or sell" in text
