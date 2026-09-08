"""Schema-level guarantees: FKs, cascades, uniqueness, relationships."""
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError

# SQLite reports a foreign-key violation as OperationalError, Postgres as
# IntegrityError; both mean "the database rejected it".
CONSTRAINT_ERROR = (IntegrityError, OperationalError)

from app.models.finance import ExpenseRecord, FinancialProfile, IncomeRecord
from app.models.goal import FinancialGoal
from app.models.market import MarketAsset, MarketSnapshot, WatchlistItem
from app.models.simulation import ChatSession, EducationProgress, Simulation
from app.models.user import User


def make_user(db, telegram_id: int = 424_242) -> User:
    user = User(telegram_id=telegram_id, locale="fa", risk_profile="moderate")
    db.add(user)
    db.flush()
    return user


def test_all_tables_are_registered():
    from app.db.base import Base

    assert set(Base.metadata.tables) == {
        "users", "financial_profiles", "income_records", "expense_records",
        "financial_goals", "market_assets", "market_snapshots", "watchlists",
        "simulations", "chat_sessions", "education_progress",
    }


def test_user_timestamps_are_populated(db):
    user = make_user(db)
    db.commit()
    assert user.created_at is not None and user.updated_at is not None


def test_telegram_id_is_unique(db):
    make_user(db, 1)
    db.commit()
    db.add(User(telegram_id=1))
    with pytest.raises(CONSTRAINT_ERROR):
        db.flush()


def test_profile_requires_an_existing_user(db):
    db.add(FinancialProfile(user_id=9999, monthly_income=1.0))
    with pytest.raises(CONSTRAINT_ERROR):
        db.flush()


def test_profile_is_one_to_one(db):
    user = make_user(db)
    db.add(FinancialProfile(user_id=user.id))
    db.commit()
    db.add(FinancialProfile(user_id=user.id))
    with pytest.raises(CONSTRAINT_ERROR):
        db.flush()


def test_relationships_are_navigable_from_the_user(db):
    user = make_user(db)
    user.profile = FinancialProfile(monthly_income=30_000_000, income_type="mixed")
    user.goals.append(FinancialGoal(name="laptop", target_amount=60_000_000, deadline=date(2027, 3, 1)))
    user.income_records.append(IncomeRecord(amount=30_000_000, period="2026-09", source="salary"))
    user.expense_records.append(
        ExpenseRecord(category="housing", amount=8_000_000, period="2026-09", is_essential=True)
    )
    user.watchlist.append(WatchlistItem(symbol="BTC"))
    user.simulations.append(Simulation(kind="what_if", params_json="{}", result_json="{}"))
    user.chat_sessions.append(ChatSession())
    user.education_progress.append(EducationProgress(topic_key="budgeting", completed=True, quiz_score=90))
    db.commit()

    db.expire_all()
    reloaded = db.get(User, user.id)
    assert reloaded.profile.monthly_income == 30_000_000
    assert [g.name for g in reloaded.goals] == ["laptop"]
    assert reloaded.expense_records[0].category == "housing"
    assert reloaded.watchlist[0].symbol == "BTC"
    assert reloaded.simulations[0].kind == "what_if"
    assert reloaded.chat_sessions[0].transcript_json == "[]"
    assert reloaded.education_progress[0].quiz_score == 90


def test_deleting_a_user_cascades_to_owned_rows(db):
    user = make_user(db)
    user.profile = FinancialProfile(monthly_income=1.0)
    user.goals.append(FinancialGoal(name="g", target_amount=1.0))
    user.expense_records.append(ExpenseRecord(category="food", amount=1.0, period="2026-09"))
    user.watchlist.append(WatchlistItem(symbol="BTC"))
    db.commit()

    db.delete(user)
    db.commit()

    for model in (FinancialProfile, FinancialGoal, ExpenseRecord, WatchlistItem):
        assert db.scalar(select(func.count()).select_from(model)) == 0


def test_expenses_are_unique_per_user_period_category(db):
    user = make_user(db)
    db.add(ExpenseRecord(user_id=user.id, category="food", amount=1.0, period="2026-09"))
    db.commit()
    db.add(ExpenseRecord(user_id=user.id, category="food", amount=2.0, period="2026-09"))
    with pytest.raises(CONSTRAINT_ERROR):
        db.flush()


def test_watchlist_entries_are_unique_per_user(db):
    user = make_user(db)
    db.add(WatchlistItem(user_id=user.id, symbol="BTC"))
    db.commit()
    db.add(WatchlistItem(user_id=user.id, symbol="BTC"))
    with pytest.raises(CONSTRAINT_ERROR):
        db.flush()


def test_education_progress_is_unique_per_topic(db):
    user = make_user(db)
    db.add(EducationProgress(user_id=user.id, topic_key="inflation"))
    db.commit()
    db.add(EducationProgress(user_id=user.id, topic_key="inflation"))
    with pytest.raises(CONSTRAINT_ERROR):
        db.flush()


def test_goal_target_must_be_positive(db):
    user = make_user(db)
    db.add(FinancialGoal(user_id=user.id, name="bad", target_amount=0))
    with pytest.raises(CONSTRAINT_ERROR):
        db.flush()


def test_market_asset_symbol_is_unique_and_snapshots_store_a_series(db):
    db.add(MarketAsset(symbol="BTC", provider_id="bitcoin", asset_class="crypto"))
    db.add(
        MarketSnapshot(
            symbol="BTC",
            as_of=datetime(2026, 9, 4, tzinfo=timezone.utc),
            points_json='[{"date": "2026-09-01", "close": 1.0}]',
        )
    )
    db.commit()

    db.add(MarketAsset(symbol="BTC", provider_id="bitcoin-2", asset_class="crypto"))
    with pytest.raises(CONSTRAINT_ERROR):
        db.flush()
