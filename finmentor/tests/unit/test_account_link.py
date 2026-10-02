"""The merge that linking a Telegram account performs.

One rule, asserted from both sides: **the web account wins every collision;
everything that does not collide moves across.** Every test here is either an
instance of that rule or a check that the rule's definition of "collision"
still matches what the database actually enforces.
"""
from __future__ import annotations

import pytest
from sqlalchemy import inspect as sa_inspect

from app.models.finance import ExpenseRecord, FinancialProfile, IncomeRecord
from app.models.goal import FinancialGoal
from app.models.market import WatchlistItem
from app.models.simulation import ChatSession, EducationProgress, Simulation
from app.models.user import User
from app.repositories import account_link
from app.repositories import users as users_repo


@pytest.fixture
def web_user(db) -> User:
    user = users_repo.create_web_user(db, email="web@finmentor.local",
                                      password_hash="x")
    db.flush()
    return user


@pytest.fixture
def bot_user(db) -> User:
    user = users_repo.create(db, telegram_id=99_001)
    db.flush()
    return user


def profile_for(db, user, income=1000.0):
    row = FinancialProfile(user_id=user.id, monthly_income=income)
    db.add(row)
    db.flush()
    return row


def goal_for(db, user, name="A goal"):
    row = FinancialGoal(user_id=user.id, name=name, target_amount=100.0,
                        current_amount=0.0, priority=1)
    db.add(row)
    db.flush()
    return row


def expense_for(db, user, period="2026-09", category="food", amount=10.0):
    row = ExpenseRecord(user_id=user.id, period=period, category=category,
                        amount=amount)
    db.add(row)
    db.flush()
    return row


def watch_for(db, user, symbol="AAPL"):
    row = WatchlistItem(user_id=user.id, symbol=symbol)
    db.add(row)
    db.flush()
    return row


def topic_for(db, user, key="budgeting", score=1):
    row = EducationProgress(user_id=user.id, topic_key=key, quiz_score=score)
    db.add(row)
    db.flush()
    return row


# --- the tables with no per-user uniqueness: everything moves -------------

def test_goals_and_income_and_simulations_all_move(db, web_user, bot_user):
    goal_for(db, bot_user, "Bot goal")
    goal_for(db, bot_user, "Another bot goal")
    db.add(IncomeRecord(user_id=bot_user.id, amount=50.0, period="2026-09"))
    db.add(Simulation(user_id=bot_user.id, kind="what_if", params_json="{}",
                      result_json="{}"))
    db.flush()

    report = account_link.merge(db, into=web_user, source=bot_user)

    assert report.moved["goal"] == 2
    assert report.moved["income record"] == 1
    assert report.moved["saved simulation"] == 1
    assert report.kept == {}
    assert {goal.name for goal in web_user.goals} == {"Bot goal", "Another bot goal"}


def test_a_duplicate_goal_survives_as_a_duplicate(db, web_user, bot_user):
    """Nothing stops the same goal existing twice, and that is deliberate.

    A visible duplicate the user can delete is a better outcome than silently
    dropping one of the two, because only one of those is reversible.
    """
    goal_for(db, web_user, "Emergency fund")
    goal_for(db, bot_user, "Emergency fund")

    account_link.merge(db, into=web_user, source=bot_user)

    assert [goal.name for goal in web_user.goals] == ["Emergency fund"] * 2


# --- the singular tables: the web row wins -------------------------------

def test_the_web_profile_wins_and_the_bot_profile_goes(db, web_user, bot_user):
    profile_for(db, web_user, income=5000.0)
    profile_for(db, bot_user, income=1234.0)

    report = account_link.merge(db, into=web_user, source=bot_user)

    assert report.kept["profile"] == 1
    assert "profile" not in report.moved
    assert web_user.profile.monthly_income == 5000.0
    assert db.query(FinancialProfile).count() == 1


def test_the_bot_profile_is_adopted_when_the_web_account_has_none(db, web_user, bot_user):
    profile_for(db, bot_user, income=1234.0)

    report = account_link.merge(db, into=web_user, source=bot_user)

    assert report.moved["profile"] == 1
    assert web_user.profile.monthly_income == 1234.0


def test_one_chat_session_survives(db, web_user, bot_user):
    """uq_chat_sessions_user means the transcript cannot simply move."""
    db.add(ChatSession(user_id=web_user.id, transcript_json='["web"]'))
    db.add(ChatSession(user_id=bot_user.id, transcript_json='["bot"]'))
    db.flush()

    report = account_link.merge(db, into=web_user, source=bot_user)

    assert report.kept["chat session"] == 1
    assert db.query(ChatSession).count() == 1
    assert db.query(ChatSession).one().transcript_json == '["web"]'


# --- the composite keys: a collision is per row, not per table -----------

def test_expenses_collide_per_period_and_category(db, web_user, bot_user):
    expense_for(db, web_user, category="food", amount=100.0)
    expense_for(db, bot_user, category="food", amount=7.0)         # collides
    expense_for(db, bot_user, category="housing", amount=8.0)      # does not
    expense_for(db, bot_user, period="2026-08", category="food")   # nor this

    report = account_link.merge(db, into=web_user, source=bot_user)

    assert report.moved["expense record"] == 2
    assert report.kept["expense record"] == 1
    kept = {(row.period, row.category): row.amount for row in
            db.query(ExpenseRecord).filter_by(user_id=web_user.id)}
    assert kept[("2026-09", "food")] == 100.0, "the web figure, not the bot one"
    assert set(kept) == {("2026-09", "food"), ("2026-09", "housing"),
                         ("2026-08", "food")}


def test_watchlist_collides_per_symbol(db, web_user, bot_user):
    watch_for(db, web_user, "AAPL")
    watch_for(db, bot_user, "AAPL")
    watch_for(db, bot_user, "MSFT")

    report = account_link.merge(db, into=web_user, source=bot_user)

    assert report.moved["watchlist symbol"] == 1
    assert report.kept["watchlist symbol"] == 1
    assert {row.symbol for row in web_user.watchlist} == {"AAPL", "MSFT"}


def test_progress_collides_per_topic(db, web_user, bot_user):
    topic_for(db, web_user, "budgeting", score=1)
    topic_for(db, bot_user, "budgeting", score=0)
    topic_for(db, bot_user, "compounding", score=1)

    report = account_link.merge(db, into=web_user, source=bot_user)

    assert report.moved["completed topic"] == 1
    rows = {row.topic_key: row.quiz_score for row in
            db.query(EducationProgress).filter_by(user_id=web_user.id)}
    assert rows == {"budgeting": 1, "compounding": 1}


# --- the identity itself -------------------------------------------------

def test_the_telegram_id_moves_and_the_source_row_goes(db, web_user, bot_user):
    telegram_id = bot_user.telegram_id
    source_id = bot_user.id

    account_link.merge(db, into=web_user, source=bot_user)

    assert web_user.telegram_id == telegram_id
    assert users_repo.get(db, source_id) is None
    assert users_repo.get_by_telegram_id(db, telegram_id).id == web_user.id


def test_the_merge_survives_a_commit(db, web_user, bot_user):
    """The unique index on telegram_id is the thing most likely to object.

    `merge` deletes the source row before assigning its id, and only a flush
    separates the two statements. If that ordering were wrong this is the test
    that would fail, and it would fail at the database rather than quietly.
    """
    goal_for(db, bot_user, "Bot goal")

    account_link.merge(db, into=web_user, source=bot_user)
    db.commit()

    assert users_repo.get_by_telegram_id(db, 99_001).email == "web@finmentor.local"


def test_nothing_to_merge_is_a_quiet_success(db, web_user, bot_user):
    """The common case: a bot row that only ever said /start."""
    report = account_link.merge(db, into=web_user, source=bot_user)

    assert report.moved == {} and report.kept == {}
    assert report.moved_anything is False
    assert web_user.telegram_id == 99_001


# --- the rule's definition of a collision stays true ---------------------

def test_every_user_owned_table_is_in_the_merge_list():
    """A new table hanging off `users` has to be added to `MERGED`.

    Without this, a table added later keeps pointing at the row the merge
    deletes and goes with it: data loss with no failing test and no error.
    The three credential tables are deliberate exceptions, because a grant
    issued to one account should not follow the data onto another.
    """
    credentials = {"password_resets", "telegram_links", "user_identities"}
    listed = {model.__tablename__ for model, _, _ in account_link.MERGED}

    owned = set()
    for mapper in User.registry.mappers:
        model = mapper.class_
        if model is User:
            continue
        columns = sa_inspect(model).columns
        if "user_id" not in columns:
            continue
        if any(fk.column.table.name == "users"
               for fk in columns["user_id"].foreign_keys):
            owned.add(model.__tablename__)

    assert owned, "the walk found no user-owned tables, so it proves nothing"
    assert owned - credentials - listed == set(), (
        "a user-owned table is missing from account_link.MERGED"
    )


def _unique_column_sets(table):
    """Every set of columns this table enforces as unique, however declared.

    `watchlists` uses a `UniqueConstraint` and `expense_records` a unique
    `Index`, so reading only one of the two would miss a real constraint.
    A `unique=True` column counts as well: that is how `financial_profiles`
    says one profile per user.
    """
    sets = [{column.name for column in constraint.columns}
            for constraint in table.constraints
            if type(constraint).__name__ == "UniqueConstraint"]
    sets += [{column.name for column in index.columns}
             for index in table.indexes if index.unique]
    sets += [{column.name} for column in table.columns if column.unique]
    return sets


@pytest.mark.parametrize("model, label, key", account_link.MERGED,
                         ids=[label for _, label, _ in account_link.MERGED])
def test_the_declared_key_matches_a_real_constraint(model, label, key):
    """`MERGED` claims which columns collide. The schema has to agree.

    A key naming columns the database does not enforce makes the merge skip
    rows for no reason. A missing key makes it try to move a row that cannot
    move, and an integrity error fails the whole link.
    """
    declared = set(key) | {"user_id"}
    per_user = [columns for columns in _unique_column_sets(model.__table__)
                if "user_id" in columns]

    if key:
        assert declared in per_user, (
            f"{model.__tablename__}: MERGED declares {sorted(declared)}, "
            f"schema enforces {[sorted(c) for c in per_user]}"
        )
    else:
        assert not per_user, (
            f"{model.__tablename__}: MERGED declares no key but the schema "
            f"enforces {[sorted(c) for c in per_user]}"
        )
