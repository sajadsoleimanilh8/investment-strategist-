"""CRUD for `telegram_links`.

Deliberately the same shape as `password_resets`: both are short-lived,
single-use, hashed grants pointing at a user, and the two reading the same way
is worth more than saving the duplication.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.auth import TelegramLink


def _as_utc(moment: datetime) -> datetime:
    """Treat a naive timestamp as UTC (SQLite drops the offset)."""
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def create(db: Session, *, user_id: int, code_hash: str,
           now: datetime | None = None) -> TelegramLink:
    now = now or datetime.now(timezone.utc)
    link = TelegramLink(
        user_id=user_id,
        code_hash=code_hash,
        expires_at=now + timedelta(minutes=settings.telegram_link_ttl_minutes),
    )
    db.add(link)
    db.flush()
    return link


def invalidate_outstanding(db: Session, user_id: int, *,
                           now: datetime | None = None) -> None:
    """Retire every unused code this user already has.

    Asking for a second code should kill the first. A code is a grant to
    attach a Telegram account to this one, and leaving a trail of live grants
    on a screen the user has walked away from is the whole risk.
    """
    db.execute(
        update(TelegramLink)
        .where(TelegramLink.user_id == user_id, TelegramLink.used_at.is_(None))
        .values(used_at=now or datetime.now(timezone.utc))
    )


def usable(db: Session, code_hash: str, *,
           now: datetime | None = None) -> TelegramLink | None:
    """The link this code unlocks, or None if there is not one.

    One answer for "no such code", "already used" and "expired", as with
    resets: the difference is not something the person holding a bad code can
    act on, and spelling it out tells an attacker which guesses were close.
    """
    now = now or datetime.now(timezone.utc)
    link = db.scalar(select(TelegramLink).where(TelegramLink.code_hash == code_hash))
    if link is None or link.used_at is not None:
        return None
    if _as_utc(link.expires_at) <= now:
        return None
    return link


def spend(db: Session, link: TelegramLink, *, now: datetime | None = None) -> None:
    link.used_at = now or datetime.now(timezone.utc)
    db.flush()
