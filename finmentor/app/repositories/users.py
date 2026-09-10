"""CRUD for `users`."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


def get(db: Session, user_id: int) -> User | None:
    return db.get(User, user_id)


def get_by_telegram_id(db: Session, telegram_id: int) -> User | None:
    return db.scalar(select(User).where(User.telegram_id == telegram_id))


def get_by_email(db: Session, email: str) -> User | None:
    """Case-insensitive: nobody expects Bob@x.com and bob@x.com to differ."""
    return db.scalar(select(User).where(User.email == normalise_email(email)))


def normalise_email(email: str) -> str:
    return (email or "").strip().lower()


def create_web_user(db: Session, *, email: str, password_hash: str,
                    locale: str = "en") -> User:
    """A user who signed up on the web. No telegram id until they link one."""
    user = User(email=normalise_email(email), password_hash=password_hash, locale=locale)
    db.add(user)
    db.flush()
    return user


def set_password(db: Session, user: User, password_hash: str) -> User:
    user.password_hash = password_hash
    db.flush()
    return user


def create(db: Session, *, telegram_id: int, locale: str = "en",
           risk_profile: str | None = None) -> User:
    user = User(telegram_id=telegram_id, locale=locale, risk_profile=risk_profile)
    db.add(user)
    db.flush()
    return user


def get_or_create(db: Session, *, telegram_id: int, locale: str = "en") -> User:
    user = get_by_telegram_id(db, telegram_id)
    if user is None:
        user = create(db, telegram_id=telegram_id, locale=locale)
    return user


def set_risk_profile(db: Session, user: User, risk_profile: str) -> User:
    user.risk_profile = risk_profile
    db.flush()
    return user


def delete(db: Session, user: User) -> None:
    """Removes the user and — via ON DELETE CASCADE — everything they own."""
    db.delete(user)
    db.flush()
