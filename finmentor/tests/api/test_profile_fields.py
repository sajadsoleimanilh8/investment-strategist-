"""Two fields a profile save used to destroy.

`PUT /api/financial-profile/{id}` is a replace, which is right for a form that
shows every field. It stops being right for a field the form does not show,
because a client that round-trips what it was given cannot send back something
it was never told.

`planned_budget` was the worse of the two. No surface sets it — not the web
app, not the bot — and the read contract did carry it, so any save wiped it.
`score_budget_stability` then fell back to its documented neutral 12/20 and
stayed there, which quietly turned a fifth of the health score into a constant.

`income_type` was the same shape with a different cause: the read contract did
not carry it at all, so `Profile.tsx` hard-coded "fixed" when seeding its form
and reset the field on every save.
"""
import pytest

PROFILE_BODY = {
    "monthly_income": 30_000_000,
    "expenses": {"housing": 8_000_000, "food": 5_000_000, "transportation": 2_000_000},
    "current_savings": 45_000_000,
    "emergency_fund": 30_000_000,
}
PLAN = {"housing": 7_000_000, "food": 4_000_000, "transportation": 2_000_000,
        "education": 0, "bills": 0, "entertainment": 0, "shopping": 0, "other": 0}


@pytest.fixture
def user_id(client) -> int:
    return client.post("/api/users", json={"telegram_id": 700_777}).json()["id"]


# --- income_type ---------------------------------------------------------

def test_the_twin_reports_the_stored_income_type(client, user_id):
    """A client can only send back a value the read gave it."""
    client.put(f"/api/financial-profile/{user_id}",
               json={**PROFILE_BODY, "income_type": "variable"})

    twin = client.get(f"/api/financial-profile/{user_id}").json()

    assert twin["income_type"] == "variable"


def test_income_type_survives_a_round_trip(client, user_id):
    """Select Variable, save, reload, save again: still Variable.

    The exact sequence from the audit. The second save is what used to lose
    it, because the form had seeded itself with a hard-coded "fixed".
    """
    client.put(f"/api/financial-profile/{user_id}",
               json={**PROFILE_BODY, "income_type": "variable"})

    reloaded = client.get(f"/api/financial-profile/{user_id}").json()
    client.put(f"/api/financial-profile/{user_id}", json={
        "monthly_income": reloaded["income"],
        "income_type": reloaded["income_type"],
        "expenses": reloaded["expenses"],
        "current_savings": reloaded["current_savings"],
        "debt": reloaded["debt"],
        "monthly_debt_payment": reloaded["monthly_debt_payment"],
        "emergency_fund": reloaded["emergency_fund"],
        "risk_profile": reloaded["risk_profile"],
    })

    assert client.get(f"/api/financial-profile/{user_id}").json()["income_type"] == "variable"


# --- planned_budget ------------------------------------------------------

def test_a_planned_budget_can_be_set_and_read_back(client, user_id):
    response = client.put(f"/api/financial-profile/{user_id}",
                          json={**PROFILE_BODY, "planned_budget": PLAN})

    assert response.status_code == 200
    assert response.json()["planned_budget"]["housing"] == 7_000_000


def test_omitting_the_planned_budget_leaves_it_alone(client, user_id):
    """The defect, in one test. A save that says nothing must change nothing."""
    client.put(f"/api/financial-profile/{user_id}",
               json={**PROFILE_BODY, "planned_budget": PLAN})

    client.put(f"/api/financial-profile/{user_id}", json=PROFILE_BODY)

    twin = client.get(f"/api/financial-profile/{user_id}").json()
    assert twin["planned_budget"] is not None, "the plan was erased by an unrelated save"
    assert twin["planned_budget"]["housing"] == 7_000_000


def test_an_explicit_null_clears_the_planned_budget(client, user_id):
    """Absence and null have to mean different things, or there is no way back."""
    client.put(f"/api/financial-profile/{user_id}",
               json={**PROFILE_BODY, "planned_budget": PLAN})

    client.put(f"/api/financial-profile/{user_id}",
               json={**PROFILE_BODY, "planned_budget": None})

    assert client.get(f"/api/financial-profile/{user_id}").json()["planned_budget"] is None


def test_the_plan_can_be_replaced_with_a_different_one(client, user_id):
    client.put(f"/api/financial-profile/{user_id}",
               json={**PROFILE_BODY, "planned_budget": PLAN})

    client.put(f"/api/financial-profile/{user_id}",
               json={**PROFILE_BODY, "planned_budget": {**PLAN, "housing": 9_000_000}})

    twin = client.get(f"/api/financial-profile/{user_id}").json()
    assert twin["planned_budget"]["housing"] == 9_000_000


# --- what the plan is actually for ---------------------------------------

def test_budget_stability_stops_being_neutral_once_a_plan_exists(client, user_id):
    """Without a plan the component scores the documented neutral 12/20.

    That is correct behaviour for a question nobody was asked. It is not
    correct as a permanent state, and until a plan could be set it was the
    only state reachable — one fifth of the score, frozen.
    """
    client.put(f"/api/financial-profile/{user_id}", json=PROFILE_BODY)
    neutral = _component(client, user_id, "budget_stability")
    assert neutral["points"] == 12.0
    assert "neutral" in neutral["detail"]

    # Spending exactly to plan is the other end of the scale.
    client.put(f"/api/financial-profile/{user_id}", json={
        **PROFILE_BODY,
        "planned_budget": {**PLAN, "housing": 8_000_000, "food": 5_000_000},
    })

    measured = _component(client, user_id, "budget_stability")
    assert measured["points"] == 20.0
    assert "deviated 0.0%" in measured["detail"]


def test_overspending_the_plan_is_measured_not_neutral(client, user_id):
    client.put(f"/api/financial-profile/{user_id}", json={
        **PROFILE_BODY,
        "planned_budget": {**PLAN, "housing": 4_000_000, "food": 2_500_000},
    })

    measured = _component(client, user_id, "budget_stability")
    assert measured["points"] < 12.0, "a real miss must score below the neutral default"
    assert "deviated" in measured["detail"]


def test_a_planned_budget_is_rejected_when_it_is_not_finite(client, user_id):
    """The plan is money like any other money on this model."""
    response = client.put(
        f"/api/financial-profile/{user_id}",
        headers={"Content-Type": "application/json"},
        content='{"monthly_income": 100, "planned_budget": {"housing": Infinity}}',
    )

    assert response.status_code == 422


def _component(client, user_id: int, name: str) -> dict:
    score = client.get(f"/api/health/{user_id}").json()
    return next(c for c in score["components"] if c["name"] == name)
