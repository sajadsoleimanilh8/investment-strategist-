"""Tables that exist for authentication rather than for finance.

Kept out of `user.py` because they are not attributes of a person: a reset is
a short-lived grant that happens to point at one, and the row is garbage the
moment it is spent.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models.user import User


class PasswordReset(Base, TimestampMixin):
    """One outstanding "email me a link" request.

    The token is stored as a SHA-256 hash, not in the clear. A reset row is a
    bearer credential: whoever holds the raw token can take the account, so a
    database leak must not hand over working links along with the hashes it
    was already going to expose. The raw value exists once, in the email.

    Single use, which is why `used_at` exists rather than the row simply being
    deleted: a second attempt with a spent token should be refused, not read
    as "no such token", and keeping the row makes that difference visible in
    the data rather than inferred from its absence.
    """

    __tablename__ = "password_resets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    #: sha256 of the token that was emailed. Fixed length, so it indexes well.
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    user: Mapped[User] = relationship(back_populates="password_resets")


class TelegramLink(Base, TimestampMixin):
    """One outstanding "connect my Telegram account" code.

    Same shape as `PasswordReset` and for the same reasons: a bearer credential
    stored as a hash, single use, with `used_at` rather than deletion so that a
    second attempt is refused instead of being read as "no such code".

    It is a weaker credential than a reset token and deliberately so. A reset
    token is 32 random bytes because it arrives by email and nobody types it; a
    link code is read off one screen and typed into another, so it is twelve
    characters from an unambiguous alphabet — about 59 bits. That is far too
    much to guess online against the limiter, and it is *not* enough to shrug
    at if the table leaks, which is why the TTL is minutes rather than an hour.
    """

    __tablename__ = "telegram_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    #: sha256 of the normalised code (upper case, no separators).
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    user: Mapped[User] = relationship(back_populates="telegram_links")
