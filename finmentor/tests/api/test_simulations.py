"""POST /api/simulations and GET /api/simulations/{user_id}."""
import pytest
from tests.conftest import error_message

PERIOD = "2026-09"
PROFILE_BODY = {
    "monthly_income": 30_000_000,
    "expenses": {"housing": 8_000_000, "food": 5_000_000, "transportation": 2_000_000,
                 "bills": 1_500_000, "entertainment": 900_000, "shopping": 600_000},
    "current_savings": 45_000_000,
    "debt": 10_000_000,
    "monthly_debt_payment": 1_500_000,
    "emergency_fund": 30_000_000,
}
LAPTOP = {"name": "Laptop", "target_amount": 60_000_000, "current_amount": 20_000_000,
          "priority": 1}


@pytest.fixture
def user_id(client, monkeypatch) -> int:
    monkeypatch.setattr("app.repositories.profiles.current_period", lambda *a, **k: PERIOD)
    uid = client.post("/api/users", json={"telegram_id": 800_001}).json()["id"]
    client.put(f"/api/financial-profile/{uid}?period={PERIOD}", json=PROFILE_BODY)
    client.post("/api/goals", json={"user_id": uid, **LAPTOP})
    return uid


@pytest.fixture
def bare_user_id(client) -> int:
    """A user with no financial profile yet."""
    return client.post("/api/users", json={"telegram_id": 800_002}).json()["id"]


# --- what_if ------------------------------------------------------------

def test_what_if_returns_both_paths_and_deltas(client, user_id):
    response = client.post("/api/simulations", json={
        "user_id": user_id, "kind": "what_if",
        "params": {"monthly_savings_delta": 5_000_000, "horizon_months": 6},
    })

    assert response.status_code == 201
    body = response.json()
    assert body["current"]["monthly_savings"] == 10_500_000
    assert body["scenario"]["monthly_savings"] == 15_500_000
    assert body["deltas"]["monthly_savings"] == 5_000_000
    assert body["deltas"]["projected_savings_end"] == 30_000_000
    assert body["disclaimer"]


def test_what_if_shifts_the_goal_date(client, user_id):
    body = client.post("/api/simulations", json={
        "user_id": user_id, "kind": "what_if",
        "params": {"monthly_savings_delta": 5_000_000},
    }).json()

    assert body["scenario"]["estimated_goal_date"] < body["current"]["estimated_goal_date"]


def test_what_if_can_target_a_specific_goal(client, user_id):
    car = client.post("/api/goals", json={
        "user_id": user_id, "name": "Car", "target_amount": 500_000_000, "priority": 4,
    }).json()

    body = client.post("/api/simulations", json={
        "user_id": user_id, "kind": "what_if",
        "params": {"monthly_savings_delta": 1_000_000, "goal_id": car["id"],
                   "horizon_months": 12},
    }).json()

    # tracking the far-off car, not the nearly-funded laptop
    assert body["current"]["goal_completion_pct"] < 50


def test_a_goal_belonging_to_someone_else_is_422(client, user_id, bare_user_id):
    other = client.post("/api/goals", json={"user_id": bare_user_id, **LAPTOP}).json()

    response = client.post("/api/simulations", json={
        "user_id": user_id, "kind": "what_if", "params": {"goal_id": other["id"]},
    })
    assert response.status_code == 422
    assert "goal_id" in error_message(response)


# --- time_machine -------------------------------------------------------

def test_time_machine_returns_the_four_paths(client, user_id):
    response = client.post("/api/simulations", json={
        "user_id": user_id, "kind": "time_machine", "params": {"horizon_months": 36},
    })

    assert response.status_code == 201
    assert [p["label"] for p in response.json()] == [
        "current", "conservative", "improved_savings", "increased_expense"
    ]


def test_time_machine_defaults_to_a_36_month_horizon(client, user_id):
    default = client.post("/api/simulations", json={
        "user_id": user_id, "kind": "time_machine", "params": {},
    }).json()
    explicit = client.post("/api/simulations", json={
        "user_id": user_id, "kind": "time_machine", "params": {"horizon_months": 36},
    }).json()

    assert default[0]["projected_savings_end"] == explicit[0]["projected_savings_end"]


# --- decision -----------------------------------------------------------

def test_decision_reports_before_and_after(client, user_id):
    response = client.post("/api/simulations", json={
        "user_id": user_id, "kind": "decision", "params": {"price": 40_000_000},
    })

    assert response.status_code == 201
    body = response.json()
    assert body["savings_before"] == 45_000_000
    assert body["savings_after"] == 5_000_000
    assert body["affordable"] is True
    assert "decision is yours" in body["disclaimer"].lower()


def test_an_unaffordable_purchase_is_still_computed(client, user_id):
    body = client.post("/api/simulations", json={
        "user_id": user_id, "kind": "decision", "params": {"price": 90_000_000},
    }).json()

    assert body["affordable"] is False
    # 45M of cash and 30M of emergency fund covered it; 15M short of the rest
    assert body["savings_after"] == -15_000_000
    assert body["emergency_months_after"] == 0.0
    assert body["health_score_after"] < body["health_score_before"]


# --- errors -------------------------------------------------------------

def test_a_user_without_a_profile_is_404(client, bare_user_id):
    response = client.post("/api/simulations", json={
        "user_id": bare_user_id, "kind": "what_if", "params": {},
    })
    assert response.status_code == 404


def test_an_unknown_user_is_404(client):
    response = client.post("/api/simulations", json={
        "user_id": 9999, "kind": "decision", "params": {"price": 1},
    })
    assert response.status_code == 404


def test_an_unknown_kind_is_422(client, user_id):
    response = client.post("/api/simulations", json={
        "user_id": user_id, "kind": "teleport", "params": {},
    })
    assert response.status_code == 422


@pytest.mark.parametrize("params", [{}, {"price": 0}, {"price": -5}, {"price": "lots"}])
def test_decision_without_a_positive_price_is_422(client, user_id, params):
    response = client.post("/api/simulations", json={
        "user_id": user_id, "kind": "decision", "params": params,
    })
    assert response.status_code == 422


@pytest.mark.parametrize("horizon", [0, -12, "soon", 1.5])
def test_a_bad_horizon_is_422(client, user_id, horizon):
    response = client.post("/api/simulations", json={
        "user_id": user_id, "kind": "time_machine", "params": {"horizon_months": horizon},
    })
    assert response.status_code == 422


def test_unusable_what_if_params_are_422(client, user_id):
    response = client.post("/api/simulations", json={
        "user_id": user_id, "kind": "what_if",
        "params": {"monthly_savings_delta": "a lot"},
    })
    assert response.status_code == 422


# --- persistence + listing ---------------------------------------------

def test_a_run_is_persisted_and_listed_back(client, user_id):
    ran = client.post("/api/simulations", json={
        "user_id": user_id, "kind": "what_if",
        "params": {"monthly_savings_delta": 5_000_000, "horizon_months": 6},
    }).json()

    listed = client.get(f"/api/simulations/{user_id}")
    assert listed.status_code == 200
    (record,) = listed.json()

    assert record["kind"] == "what_if"
    assert record["params"]["monthly_savings_delta"] == 5_000_000
    assert record["result"]["deltas"] == ran["deltas"]
    assert record["created_at"]


def test_runs_are_listed_newest_first(client, user_id):
    for price in (1_000_000, 2_000_000, 3_000_000):
        client.post("/api/simulations", json={
            "user_id": user_id, "kind": "decision", "params": {"price": price},
        })

    prices = [r["params"]["price"] for r in client.get(f"/api/simulations/{user_id}").json()]
    assert prices == [3_000_000, 2_000_000, 1_000_000]


def test_pagination(client, user_id):
    for price in (1_000_000, 2_000_000, 3_000_000):
        client.post("/api/simulations", json={
            "user_id": user_id, "kind": "decision", "params": {"price": price},
        })

    page1 = client.get(f"/api/simulations/{user_id}?limit=2").json()
    page2 = client.get(f"/api/simulations/{user_id}?limit=2&offset=2").json()

    assert [r["params"]["price"] for r in page1] == [3_000_000, 2_000_000]
    assert [r["params"]["price"] for r in page2] == [1_000_000]


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1"])
def test_invalid_pagination_is_422(client, user_id, query):
    assert client.get(f"/api/simulations/{user_id}?{query}").status_code == 422


def test_listing_for_an_unknown_user_is_404(client):
    assert client.get("/api/simulations/9999").status_code == 404


def test_a_user_with_no_runs_gets_an_empty_list(client, user_id):
    assert client.get(f"/api/simulations/{user_id}").json() == []


def test_every_kind_round_trips_through_storage(client, user_id):
    client.post("/api/simulations", json={"user_id": user_id, "kind": "what_if", "params": {}})
    client.post("/api/simulations", json={"user_id": user_id, "kind": "time_machine",
                                          "params": {"horizon_months": 12}})
    client.post("/api/simulations", json={"user_id": user_id, "kind": "decision",
                                          "params": {"price": 1_000_000}})

    kinds = [r["kind"] for r in client.get(f"/api/simulations/{user_id}").json()]
    assert kinds == ["decision", "time_machine", "what_if"]
