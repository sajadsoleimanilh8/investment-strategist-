"""GET /api/health/{user_id} and /api/health/{user_id}/dna on the demo user.

These are the deterministic paths the whole product hangs off: no LLM may be
imported, and the calculation must stay well inside the spec's 500ms budget.
"""
import sys
import time

import pytest

from scripts.seed_demo_user import DEMO_TELEGRAM_ID, seed_demo_user

PERIOD = "2026-09"
DEMO_TOTAL = 62.3


@pytest.fixture
def demo_user_id(client, db) -> int:
    """The seeded spec-section-29 user, written through the real repositories."""
    return seed_demo_user(db, period=PERIOD)


def test_health_score_for_the_demo_user(client, demo_user_id, db, monkeypatch):
    monkeypatch.setattr("app.repositories.profiles.current_period", lambda *a, **k: PERIOD)

    response = client.get(f"/api/health/{demo_user_id}")
    assert response.status_code == 200

    score = response.json()
    points = {c["name"]: c["points"] for c in score["components"]}
    assert points == {
        "savings_rate": 20.0,
        "emergency_fund": 6.1,
        "debt_load": 17.5,
        "budget_stability": 12.0,
        "goal_progress": 6.7,
    }
    assert score["total"] == DEMO_TOTAL
    assert score["total"] == pytest.approx(sum(points.values()), abs=0.05)


def test_every_component_is_reported_with_a_detail(client, demo_user_id, monkeypatch):
    monkeypatch.setattr("app.repositories.profiles.current_period", lambda *a, **k: PERIOD)

    components = client.get(f"/api/health/{demo_user_id}").json()["components"]
    assert len(components) == 5
    assert all(c["detail"] for c in components)
    assert all(c["max_points"] == 20.0 for c in components)


def test_financial_dna_for_the_demo_user(client, demo_user_id, monkeypatch):
    monkeypatch.setattr("app.repositories.profiles.current_period", lambda *a, **k: PERIOD)

    response = client.get(f"/api/health/{demo_user_id}/dna")
    assert response.status_code == 200
    assert response.json() == {
        "saving_discipline": "Strong",        # 35% savings rate
        "emergency_readiness": "Weak",        # 1.8 months of essentials
        "debt_exposure": "Strong",            # payments are 5% of income
        "goal_discipline": "Weak",            # laptop at 33%
        "budget_stability": "Moderate",       # no planned budget yet
        "financial_knowledge": "Beginner",    # no completed /learn topics
    }


def test_dna_knowledge_follows_completed_topics(client, demo_user_id, db, monkeypatch):
    monkeypatch.setattr("app.repositories.profiles.current_period", lambda *a, **k: PERIOD)
    from app.models.simulation import EducationProgress
    from app.services.education_engine import TOPICS

    for key in list(TOPICS)[:10]:
        db.add(EducationProgress(user_id=demo_user_id, topic_key=key, completed=True))
    db.commit()

    dna = client.get(f"/api/health/{demo_user_id}/dna").json()
    assert dna["financial_knowledge"] == "Advanced"


def test_a_planned_budget_raises_the_stability_component(client, demo_user_id, monkeypatch):
    monkeypatch.setattr("app.repositories.profiles.current_period", lambda *a, **k: PERIOD)
    body = {
        "monthly_income": 30_000_000,
        "expenses": {"housing": 8_000_000, "food": 5_000_000, "transportation": 2_000_000,
                     "bills": 1_500_000, "entertainment": 900_000, "shopping": 600_000},
        "planned_budget": {"housing": 8_000_000, "food": 5_000_000, "transportation": 2_000_000,
                           "bills": 1_500_000, "entertainment": 900_000, "shopping": 600_000},
        "monthly_debt_payment": 1_500_000,
        "emergency_fund": 30_000_000,
    }
    client.put(f"/api/financial-profile/{demo_user_id}?period={PERIOD}", json=body)

    score = client.get(f"/api/health/{demo_user_id}").json()
    points = {c["name"]: c["points"] for c in score["components"]}
    assert points["budget_stability"] == 20.0
    assert score["total"] == pytest.approx(DEMO_TOTAL + 8.0, abs=0.05)


def test_health_without_a_profile_is_404(client):
    user_id = client.post("/api/users", json={"telegram_id": 700_004}).json()["id"]
    assert client.get(f"/api/health/{user_id}").status_code == 404
    assert client.get(f"/api/health/{user_id}/dna").status_code == 404


def test_health_for_an_unknown_user_is_404(client):
    assert client.get("/api/health/9999").status_code == 404
    assert client.get("/api/health/9999/dna").status_code == 404


def test_health_stays_inside_the_deterministic_budget(client, demo_user_id, monkeypatch):
    """Spec section 23: deterministic calculation under 500ms."""
    monkeypatch.setattr("app.repositories.profiles.current_period", lambda *a, **k: PERIOD)
    client.get(f"/api/health/{demo_user_id}")  # warm the connection/session

    started = time.perf_counter()
    response = client.get(f"/api/health/{demo_user_id}")
    elapsed_ms = (time.perf_counter() - started) * 1000

    assert response.status_code == 200
    assert elapsed_ms < 500, f"health score took {elapsed_ms:.0f}ms"


def test_the_health_path_never_imports_the_ai_layer(client, demo_user_id, monkeypatch):
    monkeypatch.setattr("app.repositories.profiles.current_period", lambda *a, **k: PERIOD)
    for name in [n for n in sys.modules if n.startswith("app.ai")]:
        del sys.modules[name]

    client.get(f"/api/health/{demo_user_id}")
    client.get(f"/api/health/{demo_user_id}/dna")

    assert [n for n in sys.modules if n.startswith("app.ai")] == []
