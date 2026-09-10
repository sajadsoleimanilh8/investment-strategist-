"""/api/me/summary — the one call the dashboard hydrates from.

It composes existing builders rather than adding engine logic, so what matters
here is that it agrees with the routes it is composed from. A dashboard showing
a different score to `/api/health/{id}` would be worse than one showing none.
"""
import pytest

from scripts.seed_demo_user import seed_demo_user
from scripts.seed_market_assets import seed_demo_watchlist, seed_market_assets

PERIOD = "2026-09"


@pytest.fixture
def onboarded(client, db, current_user, monkeypatch):
    """The demo profile, attached to the signed-in user."""
    monkeypatch.setattr("app.repositories.profiles.current_period", lambda *a, **k: PERIOD)
    seed_demo_user(db, period=PERIOD, user=current_user)
    seed_market_assets(db)
    seed_demo_watchlist(db, current_user.id)
    db.commit()
    return current_user.id


def test_a_user_who_has_not_onboarded_gets_a_screen_not_an_error(client):
    """"You have not set this up yet" is a page, not a 404."""
    response = client.get("/api/me/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["onboarded"] is False
    assert body["twin"] is None and body["health"] is None
    assert body["goals"] == []


def test_the_summary_carries_everything_the_dashboard_needs(client, onboarded):
    body = client.get("/api/me/summary").json()

    assert body["onboarded"] is True
    assert body["twin"]["income"] > 0
    assert body["health"]["total"] > 0
    assert len(body["health"]["components"]) == 5
    assert body["dna"]["saving_discipline"] in {"Strong", "Moderate", "Weak"}
    assert body["goals"]


def test_the_score_agrees_with_the_dedicated_route(client, onboarded):
    summary = client.get("/api/me/summary").json()
    health = client.get(f"/api/health/{onboarded}").json()

    assert summary["health"]["total"] == health["total"]
    assert summary["health"]["components"] == health["components"]


def test_the_dna_agrees_with_the_dedicated_route(client, onboarded):
    summary = client.get("/api/me/summary").json()
    dna = client.get(f"/api/health/{onboarded}/dna").json()

    assert summary["dna"] == dna


def test_goals_carry_their_derived_figures(client, onboarded):
    goal = client.get("/api/me/summary").json()["goals"][0]

    assert 0 <= goal["progress_pct"] <= 100
    assert "estimated_completion" in goal
    assert goal["id"] > 0


def test_goals_are_ordered_by_priority(client, onboarded, db):
    from app.repositories import goals as goals_repo
    from app.schemas.finance import GoalIn

    goals_repo.create(db, onboarded, GoalIn(name="Low", target_amount=1_000_000, priority=5))
    goals_repo.create(db, onboarded, GoalIn(name="Top", target_amount=1_000_000, priority=1))
    db.commit()

    goals = client.get("/api/me/summary").json()["goals"]

    assert [g["priority"] for g in goals] == sorted(g["priority"] for g in goals)


def test_only_a_handful_of_goals_come_back(client, onboarded, db):
    from app.api.routes.me import TOP_GOALS
    from app.repositories import goals as goals_repo
    from app.schemas.finance import GoalIn

    for index in range(TOP_GOALS + 3):
        goals_repo.create(db, onboarded, GoalIn(name=f"G{index}", target_amount=1_000_000))
    db.commit()

    assert len(client.get("/api/me/summary").json()["goals"]) == TOP_GOALS


def test_the_watchlist_head_carries_the_market_disclaimer(client, onboarded):
    from app.schemas.market import MARKET_DISCLAIMER

    body = client.get("/api/me/summary").json()

    assert body["market_disclaimer"] == MARKET_DISCLAIMER
    assert body["watchlist"]
    assert all(item["disclaimer"] == MARKET_DISCLAIMER for item in body["watchlist"])


def test_the_watchlist_is_ranked_by_momentum(client, onboarded):
    watchlist = client.get("/api/me/summary").json()["watchlist"]

    changes = [item["change_7d_pct"] for item in watchlist]
    assert changes == sorted(changes, reverse=True)


def test_the_summary_never_calls_the_model(client, onboarded, monkeypatch):
    """A dashboard load is deterministic end to end."""
    def explode(*args, **kwargs):                       # pragma: no cover
        raise AssertionError("the dashboard reached the LLM")

    monkeypatch.setattr("app.ai.synthesizer.explain", explode)
    monkeypatch.setattr("app.ai.synthesizer.chat", explode)

    assert client.get("/api/me/summary").status_code == 200


def test_the_summary_never_fetches_from_a_provider(client, onboarded, monkeypatch):
    """The cache is warm from the seed; a dashboard must not wait on a market API."""
    def explode(*args, **kwargs):                       # pragma: no cover
        raise AssertionError("the dashboard hit a market provider")

    monkeypatch.setattr("app.market.cache._fetch_from_provider", explode, raising=False)

    assert client.get("/api/me/summary").status_code == 200
