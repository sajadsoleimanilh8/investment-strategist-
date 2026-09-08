"""market_assets, market_snapshots, watchlists."""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:  # pragma: no cover - typing only
    from app.models.user import User

ASSET_CLASSES = ("crypto", "equity")


class MarketAsset(Base, TimestampMixin):
    """A known, fetchable asset. `provider_id` is what the provider calls it."""

    __tablename__ = "market_assets"
    __table_args__ = (
        CheckConstraint("asset_class IN ('crypto', 'equity')", name="ck_market_assets_class"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(24), unique=True, index=True)  # "BTC", "AAPL"
    provider_id: Mapped[str] = mapped_column(String(64))                      # "bitcoin", "AAPL"
    asset_class: Mapped[str] = mapped_column(String(16))                      # crypto|equity
    display_name: Mapped[str] = mapped_column(String(120), default="")
    is_active: Mapped[bool] = mapped_column(default=True)


class MarketSnapshot(Base, TimestampMixin):
    """One cached daily-close series fetch, stored as JSON points."""

    __tablename__ = "market_snapshots"
    __table_args__ = (Index("ix_market_snapshots_symbol_as_of", "symbol", "as_of"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(24), index=True)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # when it was fetched
    points_json: Mapped[str] = mapped_column(Text)  # json.dumps(list[PricePoint])


class WatchlistItem(Base, TimestampMixin):
    __tablename__ = "watchlists"
    __table_args__ = (
        UniqueConstraint("user_id", "symbol", name="uq_watchlists_user_symbol"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    symbol: Mapped[str] = mapped_column(String(24), index=True)

    user: Mapped[User] = relationship(back_populates="watchlist")
