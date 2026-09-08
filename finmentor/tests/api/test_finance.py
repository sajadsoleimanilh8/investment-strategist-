"""GET/PUT /api/financial-profile/{user_id} — both return the Financial Twin."""
import pytest

from app.repositories import profiles as profiles_repo
from app.repositories import users as users_repo

PERIOD = "2026-09"

PROFILE_BODY = {
    "monthly_income": 30_000_000,
    "income_type": "mixed",
    "expenses": {"housing": 8_000_000, "food": 5_000_000, "transportation": 2_000_000,
                 "bills": 1_500_000, "entertainment": 900_000, "shopping": 600_000},
    "current_savings": 45_000_000,
    "debt": 10_000_000,
    "monthly_debt_payment": 1_500_000,
    "emergency_fund": 30_000_000,
    "risk_profile": "moderate",
}


@pytest.fixture
def user_id(client) -> int:
    return client.post("/api/users", json={"telegram_id": 700_001}).json()["id"]


def put_profile(client, user_id, **overrides):
    body = {**PROFILE_BODY, **overrides}
    return client.put(f"/api/financial-profile/{user_id}?period={PERIOD}", json=body)


def test_put_creates_the_profile_and_returns_the_twin(client, user_id):
    response = put_profile(client, user_id)

    assert response.status_code == 200
    twin = response.json()
    assert twin["income"] == 30_000_000
    assert twin["monthly_expenses"] == 18_000_000
    assert twin["essential_monthly_expenses"] == 16_500_000
    assert twin["monthly_savings"] == 10_500_000
    assert twin["savings_rate"] == 0.35
    assert twin["emergency_months"] == 1.82
    assert twin["risk_profile"] == "moderate"


def test_put_persists_through_the_repositories(client, user_id, db):
    put_profile(client, user_id)

    profile = profiles_repo.get_by_user(db, user_id)
    assert profile.monthly_income == 30_000_000
    assert profiles_repo.expense_breakdown(db, user_id, period=PERIOD).total() == 18_000_000
    assert users_repo.get(db, user_id).risk_profile == "moderate"


def test_get_returns_the_same_twin_that_put_returned(client, user_id):
    written = put_profile(client, user_id).json()

    read = client.get(f"/api/financial-profile/{user_id}?period={PERIOD}")
    assert read.status_code == 200
    assert read.json() == written


def test_put_replaces_rather_than_accumulates(client, user_id):
    put_profile(client, user_id)
    twin = put_profile(client, user_id, expenses={"housing": 1_000_000}).json()

    assert twin["monthly_expenses"] == 1_000_000
    assert twin["expenses"]["food"] == 0


def test_planned_budget_round_trips(client, user_id):
    plan = {"housing": 8_000_000, "food": 5_000_000}
    twin = put_profile(client, user_id, planned_budget=plan).json()

    assert twin["planned_budget"]["housing"] == 8_000_000
    read_back = client.get(f"/api/financial-profile/{user_id}?period={PERIOD}").json()
    assert read_back["planned_budget"]["food"] == 5_000_000


def test_expenses_are_scoped_to_their_period(client, user_id):
    put_profile(client, user_id)

    other_month = client.get(f"/api/financial-profile/{user_id}?period=2026-08").json()
    assert other_month["monthly_expenses"] == 0


def test_get_without_a_profile_is_404(client, user_id):
    response = client.get(f"/api/financial-profile/{user_id}")
    assert response.status_code == 404
    assert "profile" in response.json()["detail"]


def test_unknown_user_is_404_on_both_verbs(client):
    assert client.get("/api/financial-profile/9999").status_code == 404
    assert client.put("/api/financial-profile/9999", json=PROFILE_BODY).status_code == 404


def test_negative_income_is_rejected(client, user_id):
    response = put_profile(client, user_id, monthly_income=-1)
    assert response.status_code == 422


@pytest.mark.parametrize(
    "field", ["current_savings", "debt", "monthly_debt_payment", "emergency_fund"]
)
def test_negative_amounts_are_rejected(client, user_id, field):
    assert put_profile(client, user_id, **{field: -1}).status_code == 422


def test_a_malformed_period_is_rejected(client, user_id):
    assert client.get(f"/api/financial-profile/{user_id}?period=september").status_code == 422
