"""The bot's transaction boundary and its Telegram-id -> user mapping.

Both are small, and both are the kind of small that ruins a database: a session
that commits on a failed onboarding, or a user duplicated on every /start.
"""
import pytest

from app.bot.context import USER_ID_KEY, get_or_create_user, is_onboarded, resolve_user_id, session
from app.models.user import User
from app.repositories import users as users_repo


# --- session() ----------------------------------------------------------

def test_a_clean_exit_commits(bot_db):
    with session() as db:
        get_or_create_user(db, 900_001)

    with bot_db() as fresh:
        assert users_repo.get_by_telegram_id(fresh, 900_001) is not None


def test_an_exception_rolls_back_and_propagates(bot_db):
    with pytest.raises(RuntimeError):
        with session() as db:
            get_or_create_user(db, 900_002)
            raise RuntimeError("halfway through onboarding")

    with bot_db() as fresh:
        assert users_repo.get_by_telegram_id(fresh, 900_002) is None


def test_the_session_is_closed_either_way(bot_db):
    with session() as db:
        pass
    assert not db.in_transaction()


# --- get_or_create_user -------------------------------------------------

def test_a_new_telegram_id_creates_exactly_one_user(bot_db):
    with session() as db:
        first = get_or_create_user(db, 900_010).id
        second = get_or_create_user(db, 900_010).id

    assert first == second
    with bot_db() as fresh:
        assert fresh.query(User).filter_by(telegram_id=900_010).count() == 1


def test_a_bot_user_is_created_in_english(bot_db):
    with session() as db:
        assert get_or_create_user(db, 900_011).locale == "en"


# --- resolve_user_id ----------------------------------------------------

def test_the_user_id_is_cached_in_user_data(bot_db):
    user_data = {}
    with session() as db:
        user_id = resolve_user_id(db, user_data, 900_020)

    assert user_data[USER_ID_KEY] == user_id


def test_a_cached_id_is_reused_without_creating_another_user(bot_db):
    user_data = {}
    with session() as db:
        first = resolve_user_id(db, user_data, 900_021)
        second = resolve_user_id(db, user_data, 900_021)

    assert first == second
    with bot_db() as fresh:
        assert fresh.query(User).filter_by(telegram_id=900_021).count() == 1


def test_a_stale_cached_id_is_refreshed_rather_than_trusted(bot_db):
    """The database was reset under us; the bot must not keep pointing at a
    row that no longer exists."""
    user_data = {USER_ID_KEY: 999_999}
    with session() as db:
        user_id = resolve_user_id(db, user_data, 900_022)

    assert user_id != 999_999
    assert user_data[USER_ID_KEY] == user_id


def test_resolve_works_without_any_user_data_at_all(bot_db):
    with session() as db:
        assert resolve_user_id(db, None, 900_023) > 0


# --- is_onboarded -------------------------------------------------------

def test_a_fresh_user_is_not_onboarded(bot_db):
    with session() as db:
        assert is_onboarded(db, get_or_create_user(db, 900_030).id) is False


def test_a_user_with_a_profile_is_onboarded(bot_db, monkeypatch):
    from scripts.seed_demo_user import seed_demo_user

    monkeypatch.setattr("app.repositories.profiles.current_period", lambda *a, **k: "2026-09")
    with session() as db:
        user_id = seed_demo_user(db, period="2026-09")
        assert is_onboarded(db, user_id) is True
