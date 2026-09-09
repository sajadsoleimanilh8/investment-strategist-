"""CRUD for `market_assets`, `market_snapshots` and `watchlists`."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.market import MarketAsset, MarketSnapshot, WatchlistItem

# --- assets -------------------------------------------------------------


def list_active_assets(db: Session) -> list[MarketAsset]:
    return list(
        db.scalars(
            select(MarketAsset)
            .where(MarketAsset.is_active.is_(True))
            .order_by(MarketAsset.asset_class, MarketAsset.symbol)
        )
    )


def get_asset(db: Session, symbol: str) -> MarketAsset | None:
    """Symbols are stored upper-case; lookups are case-insensitive."""
    return db.scalar(select(MarketAsset).where(MarketAsset.symbol == symbol.upper()))


def upsert_asset(
    db: Session,
    *,
    symbol: str,
    provider_id: str,
    asset_class: str,
    display_name: str = "",
    is_active: bool = True,
) -> MarketAsset:
    asset = get_asset(db, symbol)
    if asset is None:
        asset = MarketAsset(symbol=symbol.upper())
        db.add(asset)
    asset.provider_id = provider_id
    asset.asset_class = asset_class
    asset.display_name = display_name or asset.display_name
    asset.is_active = is_active
    db.flush()
    return asset


# --- snapshots ----------------------------------------------------------


def latest_snapshot(db: Session, symbol: str) -> MarketSnapshot | None:
    return db.scalar(
        select(MarketSnapshot)
        .where(MarketSnapshot.symbol == symbol.upper())
        .order_by(MarketSnapshot.as_of.desc(), MarketSnapshot.id.desc())
        .limit(1)
    )


def add_snapshot(
    db: Session, *, symbol: str, as_of: datetime, points_json: str
) -> MarketSnapshot:
    snapshot = MarketSnapshot(symbol=symbol.upper(), as_of=as_of, points_json=points_json)
    db.add(snapshot)
    db.flush()
    return snapshot


# --- watchlist ----------------------------------------------------------


def list_watchlist(db: Session, user_id: int) -> list[WatchlistItem]:
    return list(
        db.scalars(
            select(WatchlistItem)
            .where(WatchlistItem.user_id == user_id)
            .order_by(WatchlistItem.id)
        )
    )


def add_to_watchlist(db: Session, user_id: int, symbol: str) -> WatchlistItem:
    """Idempotent: `uq_watchlists_user_symbol` allows one row per (user, symbol)."""
    symbol = symbol.upper()
    existing = db.scalar(
        select(WatchlistItem).where(
            WatchlistItem.user_id == user_id, WatchlistItem.symbol == symbol
        )
    )
    if existing is not None:
        return existing

    item = WatchlistItem(user_id=user_id, symbol=symbol)
    db.add(item)
    db.flush()
    return item


def remove_from_watchlist(db: Session, user_id: int, symbol: str) -> None:
    db.execute(
        delete(WatchlistItem).where(
            WatchlistItem.user_id == user_id, WatchlistItem.symbol == symbol.upper()
        )
    )
    db.flush()
