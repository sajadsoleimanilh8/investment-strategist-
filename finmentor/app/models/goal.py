"""financial_goals."""
from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models.user import User


class FinancialGoal(Base, TimestampMixin):
    __tablename__ = "financial_goals"
    __table_args__ = (
        Index("ix_financial_goals_user_active", "user_id", "is_active"),
        CheckConstraint("target_amount > 0", name="ck_financial_goals_target_positive"),
        CheckConstraint("current_amount >= 0", name="ck_financial_goals_current_non_negative"),
        CheckConstraint("priority BETWEEN 1 AND 5", name="ck_financial_goals_priority_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    target_amount: Mapped[float] = mapped_column(Float)
    current_amount: Mapped[float] = mapped_column(Float, default=0.0)
    deadline: Mapped[date | None] = mapped_column(Date, default=None)
    priority: Mapped[int] = mapped_column(default=3)  # 1 = highest
    is_active: Mapped[bool] = mapped_column(default=True)

    user: Mapped[User] = relationship(back_populates="goals")
