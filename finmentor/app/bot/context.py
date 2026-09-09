"""Session and user plumbing shared by every handler.

The bot is a delivery layer: it owns the transaction boundary and the mapping
from a Telegram account to a FinMentor user, and nothing else. Every number it
shows was computed in `app/services`; every explanation came from `app/api/ask`.
"""
from __future__ import annotations

from collections.abc import Iterator, MutableMapping
from contextlib import contextmanager

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.user import User
from app.repositories import profiles as profiles_repo
from app.repositories import users as users_repo

#: Where the resolved FinMentor user id is cached between updates.
USER_ID_KEY = "finmentor_user_id"


@contextmanager
def session() -> Iterator[Session]:
    """A unit of work: commit on a clean exit, roll back on anything else.

    Handlers never commit by hand, so a handler that raises halfway through
    onboarding leaves no half-written profile behind.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_or_create_user(db: Session, telegram_id: int, locale: str = "en") -> User:
    """The FinMentor user behind this Telegram account, created on first sight.

    Called from every entry point rather than only from /start, so a user who
    joined through a deep link or an inline button still resolves.
    """
    return users_repo.get_or_create(db, telegram_id=telegram_id, locale=locale)


def resolve_user_id(db: Session, user_data: MutableMapping | None, telegram_id: int) -> int:
    """The internal user id, cached in `user_data` and refreshed when missing.

    Takes the mapping rather than the PTB context so it can be called from a
    worker thread, and tested with a plain dict.
    """
    cached = user_data.get(USER_ID_KEY) if user_data is not None else None
    if cached is not None and users_repo.get(db, cached) is not None:
        return cached

    user_id = get_or_create_user(db, telegram_id).id
    if user_data is not None:
        user_data[USER_ID_KEY] = user_id
    return user_id


def is_onboarded(db: Session, user_id: int) -> bool:
    """Has this user given us enough to compute anything?"""
    return profiles_repo.get_by_user(db, user_id) is not None
