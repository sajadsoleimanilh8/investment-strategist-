"""users table. Minimal PII: Telegram id + locale only (spec section 26)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models.auth import PasswordReset
    from app.models.identity import UserIdentity
    from app.models.finance import ExpenseRecord, FinancialProfile, IncomeRecord
    from app.models.goal import FinancialGoal
    from app.models.market import WatchlistItem
    from app.models.simulation import ChatSession, EducationProgress, Simulation

RISK_PROFILES = ("conservative", "moderate", "aggressive")


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "risk_profile IS NULL OR risk_profile IN ('conservative', 'moderate', 'aggressive')",
            name="ck_users_risk_profile",
        ),
        # Two ways in, and a row must have at least one of them. A Telegram
        # user never authenticates; a web user has no telegram id. The same row
        # can hold both once the two identities are linked.
        # Three ways in now, and a row must have at least one. A Telegram user
        # never authenticates; a web user has an email; someone who arrived
        # through Google has an email too, because every provider this app
        # supports gives us one. The constraint stays as it was for that
        # reason — it is not loosened to accommodate providers, it already
        # covers them.
        CheckConstraint(
            "telegram_id IS NOT NULL OR email IS NOT NULL",
            name="ck_users_has_an_identity",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int | None] = mapped_column(
        BigInteger, unique=True, index=True, default=None
    )
    email: Mapped[str | None] = mapped_column(String(320), unique=True, index=True,
                                              default=None)
    password_hash: Mapped[str | None] = mapped_column(String(255), default=None)
    locale: Mapped[str] = mapped_column(String(8), default="en")
    #: Bumped whenever every existing session must stop working — today, a
    #: completed password reset. Tokens carry the version they were minted
    #: under and are refused when it no longer matches.
    #:
    #: A counter rather than a timestamp, and that is not a detail. The
    #: obvious design is "refuse tokens issued before the reset", but `iat` is
    #: whole seconds, so a token minted in the same second as the reset
    #: survives it — and a cutoff placed one second later would refuse the
    #: pair the reset itself hands back. A counter has no such window: it
    #: changes, and everything minted under the old value is dead immediately.
    token_version: Mapped[int] = mapped_column(default=0, server_default="0")
    risk_profile: Mapped[str | None] = mapped_column(String(16), default=None)

    profile: Mapped[FinancialProfile | None] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan", passive_deletes=True
    )
    goals: Mapped[list[FinancialGoal]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    income_records: Mapped[list[IncomeRecord]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    expense_records: Mapped[list[ExpenseRecord]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    watchlist: Mapped[list[WatchlistItem]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    simulations: Mapped[list[Simulation]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    password_resets: Mapped[list[PasswordReset]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    identities: Mapped[list[UserIdentity]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    chat_sessions: Mapped[list[ChatSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    education_progress: Mapped[list[EducationProgress]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
