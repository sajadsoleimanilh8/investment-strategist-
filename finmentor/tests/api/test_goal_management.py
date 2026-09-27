"""Managing a goal after it exists.

A goal could be created and then never touched again. `current_amount` was
fixed at creation, so `progress_pct` could not move, `score_goal_progress`
could not move, and a fifth of the health score was as frozen as the
budget-stability fifth next to it. There was no way to finish a goal and no
way to remove one created by mistake.

`is_active` is the sharper case. The column existed, `list_for_user` filtered
on it, and the web client's TypeScript declared `is_active?: boolean` on the
update payload — but no route read it, so a client could send it and watch
nothing happen. A type that describes behaviour the server does not have is
worse than a missing feature.
"""
import pytest

PROFILE = {
    "monthly_income": 30_000_000,
    "expenses": {"housing": 8_000_000, "food": 5_000_000, "transportation": 2_000_000},
    "monthly_debt_payment": 1_500_000,
    "emergency_fund": 30_000_000,
}
LAPTOP = {"name": "Laptop", "target_amount": 60_000_000,
          "current_amount": 20_000_000, "priority": 1}


@pytest.fixture
def user_id(client) -> int:
    user_id = client.post("/api/users", json={"telegram_id": 700_888}).json()["id"]
    client.put(f"/api/financial-profile/{user_id}", json=PROFILE)
    return user_id


@pytest.fixture
def goal(client, user_id) -> dict:
    return client.post("/api/goals", json={"user_id": user_id, **LAPTOP}).json()


# --- recording progress --------------------------------------------------

def test_saving_more_toward_a_goal_moves_its_progress(client, goal):
    """The loop the product is built around, and the one that did not close."""
    assert goal["progress_pct"] == 33.3

    updated = client.put(f"/api/goals/{goal['id']}",
                         json={**LAPTOP, "current_amount": 45_000_000}).json()

    assert updated["current_amount"] == 45_000_000
    assert updated["progress_pct"] == 75.0


def test_progress_moves_the_health_score(client, user_id, goal):
    """Progress is 20 of the 100 points. If it cannot move, they cannot."""
    before = _component(client, user_id, "goal_progress")["points"]

    client.put(f"/api/goals/{goal['id']}",
               json={**LAPTOP, "current_amount": 60_000_000})

    after = _component(client, user_id, "goal_progress")["points"]
    assert after > before
    assert after == 20.0, "a fully funded goal scores the component out"


def test_progress_never_exceeds_the_target(client, goal):
    """Over-saving is not 150% done; the engine already clamps and this keeps
    the route honest about it."""
    updated = client.put(f"/api/goals/{goal['id']}",
                         json={**LAPTOP, "current_amount": 90_000_000}).json()

    assert updated["progress_pct"] == 100.0


def test_the_eta_moves_with_the_amount_saved(client, goal):
    """The date is the reason to record progress at all."""
    original = goal["estimated_completion"]

    updated = client.put(f"/api/goals/{goal['id']}",
                         json={**LAPTOP, "current_amount": 55_000_000}).json()

    assert updated["estimated_completion"] < original


# --- archiving -----------------------------------------------------------

def test_archiving_a_goal_takes_it_out_of_the_active_list(client, user_id, goal):
    """`is_active: false` was declared by the client and ignored by the API."""
    response = client.put(f"/api/goals/{goal['id']}",
                          json={**LAPTOP, "is_active": False})

    assert response.status_code == 200
    assert response.json()["is_active"] is False
    assert client.get(f"/api/goals/{user_id}").json() == []


def test_an_archived_goal_is_still_there_to_look_at(client, user_id, goal):
    """Archiving is not deleting. `active_only=false` is how you see them."""
    client.put(f"/api/goals/{goal['id']}", json={**LAPTOP, "is_active": False})

    everything = client.get(f"/api/goals/{user_id}?active_only=false").json()

    assert [g["name"] for g in everything] == ["Laptop"]
    assert everything[0]["is_active"] is False


def test_an_archived_goal_can_be_restored(client, user_id, goal):
    client.put(f"/api/goals/{goal['id']}", json={**LAPTOP, "is_active": False})

    client.put(f"/api/goals/{goal['id']}", json={**LAPTOP, "is_active": True})

    assert len(client.get(f"/api/goals/{user_id}").json()) == 1


def test_omitting_is_active_leaves_the_goal_where_it_is(client, user_id, goal):
    """Same reasoning as `planned_budget`: absence is not a value.

    An edit that says nothing about archiving must not un-archive a goal, or
    every correction to an archived goal would quietly resurrect it.
    """
    client.put(f"/api/goals/{goal['id']}", json={**LAPTOP, "is_active": False})

    client.put(f"/api/goals/{goal['id']}", json={**LAPTOP, "name": "Laptop (2026)"})

    archived = client.get(f"/api/goals/{user_id}?active_only=false").json()
    assert archived[0]["is_active"] is False
    assert archived[0]["name"] == "Laptop (2026)"


def test_an_archived_goal_stops_counting_toward_the_score(client, user_id, goal):
    """Archiving has to mean something to the engine, not just to the list.

    With the only goal archived there are no goals to measure, so the
    component returns to its documented neutral rather than scoring the
    abandoned one.
    """
    client.put(f"/api/goals/{goal['id']}", json={**LAPTOP, "is_active": False})

    assert _component(client, user_id, "goal_progress")["points"] == 12.0


# --- deleting ------------------------------------------------------------

def test_deleting_a_goal_removes_it(client, user_id, goal):
    response = client.delete(f"/api/goals/{goal['id']}")

    assert response.status_code == 204
    assert client.get(f"/api/goals/{user_id}?active_only=false").json() == []


def test_deleting_a_goal_that_does_not_exist_is_404(client):
    assert client.delete("/api/goals/999999").status_code == 404


def test_deleting_does_not_disturb_the_other_goals(client, user_id, goal):
    other = client.post("/api/goals", json={
        "user_id": user_id, "name": "Phone", "target_amount": 10_000_000,
        "current_amount": 1_000_000, "priority": 3,
    }).json()

    client.delete(f"/api/goals/{goal['id']}")

    remaining = client.get(f"/api/goals/{user_id}").json()
    assert [g["id"] for g in remaining] == [other["id"]]


# --- the bounds still apply ----------------------------------------------

def test_an_update_is_validated_like_a_creation(client, goal):
    """The stricter money rules are on `GoalIn`, and `GoalUpdate` extends it."""
    assert client.put(f"/api/goals/{goal['id']}",
                      json={**LAPTOP, "target_amount": 0}).status_code == 422
    assert client.put(f"/api/goals/{goal['id']}",
                      json={**LAPTOP, "current_amount": -1}).status_code == 422
    assert client.put(f"/api/goals/{goal['id']}",
                      json={**LAPTOP, "priority": 9}).status_code == 422


def _component(client, user_id: int, name: str) -> dict:
    score = client.get(f"/api/health/{user_id}").json()
    return next(c for c in score["components"] if c["name"] == name)
