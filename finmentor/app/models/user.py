"""users table. Minimal PII: Telegram id + locale only (spec section 26)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:  # pragma: no cover - typing only
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
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    locale: Mapped[str] = mapped_column(String(8), default="fa")
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
    chat_sessions: Mapped[list[ChatSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    education_progress: Mapped[list[EducationProgress]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
