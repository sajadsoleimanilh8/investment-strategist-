"""Repository behaviour: user lookup, profile upsert, expense replacement, goals."""
import pytest

from app.repositories import goals as goals_repo
from app.repositories import profiles as profiles_repo
from app.repositories import users as users_repo
from app.schemas.finance import ExpenseBreakdown, FinancialProfileIn, GoalIn

PERIOD = "2026-09"


def profile_in(**overrides) -> FinancialProfileIn:
    data = {
        "monthly_income": 30_000_000,
        "income_type": "mixed",
        "expenses": ExpenseBreakdown(housing=8_000_000, food=5_000_000),
        "current_savings": 45_000_000,
        "debt": 10_000_000,
        "monthly_debt_payment": 1_500_000,
        "emergency_fund": 30_000_000,
        "risk_profile": "moderate",
    }
    data.update(overrides)
    return FinancialProfileIn(**data)


def test_get_or_create_is_idempotent(db):
    first = users_repo.get_or_create(db, telegram_id=7)
    second = users_repo.get_or_create(db, telegram_id=7)
    assert first.id == second.id
    assert users_repo.get(db, first.id) is first
    assert users_repo.get_by_telegram_id(db, 7).id == first.id


def test_get_returns_none_for_unknown_user(db):
    assert users_repo.get(db, 12345) is None
    assert users_repo.get_by_telegram_id(db, 12345) is None


def test_upsert_creates_then_updates_the_same_profile(db):
    user = users_repo.create(db, telegram_id=8)
    created = profiles_repo.upsert(db, user, profile_in(), period=PERIOD)
    updated = profiles_repo.upsert(db, user, profile_in(monthly_income=40_000_000), period=PERIOD)

    assert created.id == updated.id
    assert updated.monthly_income == 40_000_000
    assert user.risk_profile == "moderate"


def test_upsert_replaces_expenses_for_the_period(db):
    user = users_repo.create(db, telegram_id=9)
    profiles_repo.upsert(db, user, profile_in(), period=PERIOD)
    profiles_repo.upsert(
        db, user, profile_in(expenses=ExpenseBreakdown(housing=1_000_000)), period=PERIOD
    )

    breakdown = profiles_repo.expense_breakdown(db, user.id, period=PERIOD)
    assert breakdown.housing == 1_000_000
    assert breakdown.food == 0
    assert breakdown.total() == 1_000_000


def test_expenses_are_scoped_to_their_period(db):
    user = users_repo.create(db, telegram_id=10)
    profiles_repo.upsert(db, user, profile_in(), period="2026-08")
    profiles_repo.upsert(
        db, user, profile_in(expenses=ExpenseBreakdown(food=2_000_000)), period="2026-09"
    )

    assert profiles_repo.expense_breakdown(db, user.id, period="2026-08").housing == 8_000_000
    assert profiles_repo.expense_breakdown(db, user.id, period="2026-09").housing == 0


def test_essential_categories_are_flagged(db):
    user = users_repo.create(db, telegram_id=11)
    profiles_repo.upsert(
        db,
        user,
        profile_in(expenses=ExpenseBreakdown(housing=1, entertainment=1)),
        period=PERIOD,
    )
    flags = {r.category: r.is_essential for r in user.expense_records}
    assert flags["housing"] is True
    assert flags["entertainment"] is False


def test_to_profile_in_round_trips_through_the_database(db):
    user = users_repo.create(db, telegram_id=12)
    original = profile_in()
    profile = profiles_repo.upsert(db, user, original, period=PERIOD)
    db.commit()

    restored = profiles_repo.to_profile_in(db, profile, period=PERIOD)
    assert restored.monthly_income == original.monthly_income
    assert restored.expenses.total() == original.expenses.total()
    assert restored.risk_profile == "moderate"


def test_current_period_is_year_month():
    from datetime import date

    assert profiles_repo.current_period(date(2026, 9, 4)) == "2026-09"


def test_goal_crud_and_ordering(db):
    user = users_repo.create(db, telegram_id=13)
    goals_repo.create(db, user.id, GoalIn(name="car", target_amount=500_000_000, priority=3))
    laptop = goals_repo.create(
        db, user.id, GoalIn(name="laptop", target_amount=60_000_000, current_amount=20_000_000, priority=1)
    )

    assert [g.name for g in goals_repo.list_for_user(db, user.id)] == ["laptop", "car"]

    goals_repo.update(db, laptop, GoalIn(name="laptop", target_amount=70_000_000, priority=1))
    assert goals_repo.get(db, laptop.id).target_amount == 70_000_000
    assert goals_repo.to_goal_in(laptop).name == "laptop"


def test_inactive_goals_are_hidden_by_default(db):
    user = users_repo.create(db, telegram_id=14)
    goal = goals_repo.create(db, user.id, GoalIn(name="old", target_amount=1_000))
    goal.is_active = False
    db.flush()

    assert goals_repo.list_for_user(db, user.id) == []
    assert len(goals_repo.list_for_user(db, user.id, active_only=False)) == 1


def test_goal_input_rejects_a_non_positive_target():
    with pytest.raises(ValueError):
        GoalIn(name="bad", target_amount=0)
