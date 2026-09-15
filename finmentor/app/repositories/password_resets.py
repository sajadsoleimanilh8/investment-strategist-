"""CRUD for `password_resets`."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.auth import PasswordReset
from app.models.user import User


def _as_utc(moment: datetime) -> datetime:
    """Treat a naive timestamp as UTC (SQLite drops the offset)."""
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def create(db: Session, *, user_id: int, token_hash: str,
           now: datetime | None = None) -> PasswordReset:
    now = now or datetime.now(timezone.utc)
    reset = PasswordReset(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=now + timedelta(minutes=settings.password_reset_ttl_minutes),
    )
    db.add(reset)
    db.flush()
    return reset


def invalidate_outstanding(db: Session, user_id: int, *,
                           now: datetime | None = None) -> None:
    """Spend every unused reset this user already has.

    Asking for a second link should retire the first. Otherwise every request
    leaves another working key to the account lying in an inbox, and the
    person who forgets their password twice in a morning is the one most
    likely to be having their mail read.
    """
    db.execute(
        update(PasswordReset)
        .where(PasswordReset.user_id == user_id, PasswordReset.used_at.is_(None))
        .values(used_at=now or datetime.now(timezone.utc))
    )


def usable(db: Session, token_hash: str, *,
           now: datetime | None = None) -> PasswordReset | None:
    """The reset this token unlocks, or None if there is not one.

    One answer for "no such token", "already used" and "expired" on purpose:
    the caller turns all three into the same refusal, and the difference is
    not a distinction the person holding a bad link can act on.
    """
    now = now or datetime.now(timezone.utc)
    reset = db.scalar(select(PasswordReset).where(PasswordReset.token_hash == token_hash))
    if reset is None or reset.used_at is not None:
        return None
    if _as_utc(reset.expires_at) <= now:
        return None
    return reset


def spend(db: Session, reset: PasswordReset, *, now: datetime | None = None) -> None:
    reset.used_at = now or datetime.now(timezone.utc)
    db.flush()


def end_existing_sessions(db: Session, user: User) -> None:
    """Retire every token this account has already handed out.

    A reset exists because the old password may be in someone else's hands,
    and a session that password started is exactly what the reset is supposed
    to end. Bumping the version does it for access and refresh tokens at once,
    with no window: the pair this request is about to mint carries the new
    value, and everything older carries the old one.
    """
    user.token_version += 1
    db.flush()
