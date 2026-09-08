"""GET /api/goals/{user_id}, POST /api/goals, PUT /api/goals/{goal_id}."""
from datetime import date

import pytest

from app.repositories import goals as goals_repo
from app.services.goal_engine import add_months

PERIOD = "2026-09"
PROFILE_BODY = {
    "monthly_income": 30_000_000,
    "expenses": {"housing": 8_000_000, "food": 5_000_000, "transportation": 2_000_000,
                 "bills": 1_500_000, "entertainment": 900_000, "shopping": 600_000},
    "monthly_debt_payment": 1_500_000,
    "emergency_fund": 30_000_000,
}
LAPTOP = {"name": "Laptop", "target_amount": 60_000_000, "current_amount": 20_000_000,
          "priority": 1}


@pytest.fixture
def user_id(client) -> int:
    user_id = client.post("/api/users", json={"telegram_id": 700_002}).json()["id"]
    client.put(f"/api/financial-profile/{user_id}?period={PERIOD}", json=PROFILE_BODY)
    return user_id


def test_create_goal_returns_the_stored_goal_with_engine_figures(client, user_id):
    response = client.post("/api/goals", json={"user_id": user_id, **LAPTOP})

    assert response.status_code == 201
    goal = response.json()
    assert goal["id"] > 0
    assert goal["name"] == "Laptop"
    assert goal["is_active"] is True
    assert goal["progress_pct"] == 33.3
    # 40M remaining at the profile's 10.5M/month -> 4 months out
    assert goal["estimated_completion"] == add_months(date.today(), 4).isoformat()


def test_created_goal_is_listed(client, user_id):
    created = client.post("/api/goals", json={"user_id": user_id, **LAPTOP}).json()

    listed = client.get(f"/api/goals/{user_id}")
    assert listed.status_code == 200
    assert listed.json() == [created]


def test_goals_are_listed_highest_priority_first(client, user_id):
    client.post("/api/goals", json={"user_id": user_id, "name": "car",
                                    "target_amount": 500_000_000, "priority": 4})
    client.post("/api/goals", json={"user_id": user_id, **LAPTOP})

    assert [g["name"] for g in client.get(f"/api/goals/{user_id}").json()] == ["Laptop", "car"]


def test_update_goal_changes_the_figures(client, user_id):
    goal_id = client.post("/api/goals", json={"user_id": user_id, **LAPTOP}).json()["id"]

    updated = client.put(f"/api/goals/{goal_id}",
                         json={**LAPTOP, "current_amount": 60_000_000})
    assert updated.status_code == 200
    assert updated.json()["progress_pct"] == 100.0
    assert updated.json()["estimated_completion"] == date.today().isoformat()


def test_inactive_goals_are_hidden_unless_asked_for(client, user_id, db):
    goal_id = client.post("/api/goals", json={"user_id": user_id, **LAPTOP}).json()["id"]
    goals_repo.get(db, goal_id).is_active = False
    db.commit()

    assert client.get(f"/api/goals/{user_id}").json() == []
    assert len(client.get(f"/api/goals/{user_id}?active_only=false").json()) == 1


def test_goal_without_a_profile_has_no_eta(client):
    user_id = client.post("/api/users", json={"telegram_id": 700_003}).json()["id"]

    goal = client.post("/api/goals", json={"user_id": user_id, **LAPTOP}).json()
    assert goal["progress_pct"] == 33.3
    assert goal["estimated_completion"] is None


def test_goals_for_an_unknown_user_are_404(client):
    assert client.get("/api/goals/9999").status_code == 404
    assert client.post("/api/goals", json={"user_id": 9999, **LAPTOP}).status_code == 404


def test_updating_an_unknown_goal_is_404(client):
    assert client.put("/api/goals/9999", json=LAPTOP).status_code == 404


@pytest.mark.parametrize(
    "invalid",
    [
        {"target_amount": 0},          # must be positive
        {"target_amount": -5},
        {"current_amount": -1},
        {"priority": 0},               # 1..5
        {"priority": 9},
        {"name": ""},
    ],
)
def test_invalid_goal_payloads_are_422(client, user_id, invalid):
    body = {"user_id": user_id, **LAPTOP, **invalid}
    assert client.post("/api/goals", json=body).status_code == 422


def test_goal_deadline_round_trips(client, user_id):
    body = {"user_id": user_id, **LAPTOP, "deadline": "2027-03-01"}
    assert client.post("/api/goals", json=body).json()["deadline"] == "2027-03-01"
