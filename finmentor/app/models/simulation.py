"""simulations, chat_sessions, education_progress."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint, ForeignKey, Index, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models.user import User

SIMULATION_KINDS = ("what_if", "time_machine", "decision")


class Simulation(Base, TimestampMixin):
    """A saved deterministic scenario run. `result_json` is engine output only."""

    __tablename__ = "simulations"
    __table_args__ = (
        Index("ix_simulations_user_kind", "user_id", "kind"),
        CheckConstraint(
            "kind IN ('what_if', 'time_machine', 'decision')", name="ck_simulations_kind"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    params_json: Mapped[str] = mapped_column(Text)   # structured scenario params
    result_json: Mapped[str] = mapped_column(Text)   # deterministic engine output

    user: Mapped[User] = relationship(back_populates="simulations")


class ChatSession(Base, TimestampMixin):
    """One per user. The AI transcript.

    The uniqueness is the point. `chat_repo.get_or_create` reads the newest
    session and creates one when there is none, so two concurrent `/ask`
    requests could both find nothing and both insert — after which the older
    row was unreachable, because every read takes the newer one. The
    `order_by` hid the problem rather than preventing it.
    """

    __tablename__ = "chat_sessions"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_chat_sessions_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    transcript_json: Mapped[str] = mapped_column(Text, default="[]")

    user: Mapped[User] = relationship(back_populates="chat_sessions")


class EducationProgress(Base, TimestampMixin):
    __tablename__ = "education_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "topic_key", name="uq_education_progress_user_topic"),
        CheckConstraint(
            "quiz_score IS NULL OR quiz_score BETWEEN 0 AND 100",
            name="ck_education_progress_quiz_score",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    topic_key: Mapped[str] = mapped_column(String(48))
    completed: Mapped[bool] = mapped_column(default=False)
    quiz_score: Mapped[int | None] = mapped_column(default=None)

    user: Mapped[User] = relationship(back_populates="education_progress")
