"""The demo seed must reproduce spec section 29 exactly, and stay idempotent."""
from app.repositories import goals as goals_repo
from app.repositories import profiles as profiles_repo
from app.repositories import users as users_repo
from app.services.financial_twin import build_twin
from scripts.seed_demo_user import DEMO_TELEGRAM_ID, seed_demo_user

PERIOD = "2026-09"


def test_seed_writes_the_spec_figures(db):
    user_id = seed_demo_user(db, period=PERIOD)
    profile = profiles_repo.get_by_user(db, user_id)

    assert profile.monthly_income == 30_000_000
    assert profile.current_savings == 45_000_000
    assert profile.emergency_fund == 30_000_000
    assert profile.debt == 10_000_000
    assert profiles_repo.expense_breakdown(db, user_id, period=PERIOD).total() == 18_000_000


def test_seed_writes_the_laptop_goal(db):
    user_id = seed_demo_user(db, period=PERIOD)
    (goal,) = goals_repo.list_for_user(db, user_id)

    assert goal.name == "Laptop"
    assert goal.target_amount == 60_000_000
    assert goal.current_amount == 20_000_000
    assert goal.priority == 1
    assert goal.deadline is not None
    assert 175 <= (goal.deadline - goal.created_at.date()).days <= 185  # ~6 months


def test_seed_is_idempotent(db):
    first = seed_demo_user(db, period=PERIOD)
    second = seed_demo_user(db, period=PERIOD)

    assert first == second
    assert len(goals_repo.list_for_user(db, first)) == 1
    assert users_repo.get_by_telegram_id(db, DEMO_TELEGRAM_ID).id == first


def test_seeded_data_rebuilds_the_financial_twin(db):
    user_id = seed_demo_user(db, period=PERIOD)
    profile = profiles_repo.get_by_user(db, user_id)
    twin = build_twin(
        profiles_repo.to_profile_in(db, profile, period=PERIOD),
        [goals_repo.to_goal_in(g) for g in goals_repo.list_for_user(db, user_id)],
    )

    assert twin.income == 30_000_000
    assert twin.monthly_expenses == 18_000_000
    assert twin.essential_monthly_expenses == 16_500_000
    assert twin.monthly_savings == 10_500_000        # 30M - 18M - 1.5M debt payment
    assert twin.savings_rate == 0.35
    assert twin.emergency_months == 1.82             # 30M / 16.5M
    assert twin.risk_profile == "moderate"
    assert [g.name for g in twin.goals] == ["Laptop"]
