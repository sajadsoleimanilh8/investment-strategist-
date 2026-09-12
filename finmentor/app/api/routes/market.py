"""market routes (spec section 22): assets, one asset's trend, and the
per-user watchlist.

Every payload carries `MARKET_DISCLAIMER` (spec section 27) — the schema
defaults supply it, and no route overrides it.

Reads go through `app.market.cache`, so a warm cache answers a request without
touching a provider. `GET /api/market/assets` is deliberately cache-only: it
would otherwise fan out one provider call per listed asset, which is exactly
what section 24 says must never sit on the request path.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import DbSession, OwnedUserId, load_user, require_user
from app.market import cache
from app.models.market import MarketAsset
from app.repositories import market as market_repo
from app.schemas.market import (
    AssetListOut, MarketAssetOut, TrendReportOut, WatchlistIn, WatchlistOut,
)
from app.services import market_engine

#: Guarded at the router, not per route: a route added here later is
#: protected by default instead of by remembering.
router = APIRouter(prefix="/api", tags=["market"],
                   dependencies=[Depends(require_user)])

DEFAULT_DAYS = 30


def _known_asset(db, symbol: str) -> MarketAsset:
    asset = market_repo.get_asset(db, symbol)
    if asset is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown symbol: {symbol}"
        )
    return asset


def _cached_trend(db, symbol: str) -> TrendReportOut | None:
    """Analyse whatever is already cached; never fetch."""
    points = cache.get_cached_series(db, symbol, days=1)
    return market_engine.analyze(symbol, points) if points else None


@router.get("/market/assets", response_model=AssetListOut)
def list_assets(db: DbSession) -> AssetListOut:
    """Known assets, each with its latest cached trend if one exists."""
    return AssetListOut(
        items=[
            MarketAssetOut(
                symbol=asset.symbol,
                display_name=asset.display_name,
                asset_class=asset.asset_class,
                trend=_cached_trend(db, asset.symbol),
            )
            for asset in market_repo.list_active_assets(db)
        ]
    )


@router.get("/market/assets/{symbol}", response_model=TrendReportOut)
def get_asset_trend(symbol: str, db: DbSession, days: int = DEFAULT_DAYS) -> TrendReportOut:
    asset = _known_asset(db, symbol)
    points = cache.get_or_fetch(db, asset.symbol, days=days)
    db.commit()
    return market_engine.analyze(asset.symbol, points)


@router.get("/market/watchlist/{user_id}", response_model=WatchlistOut)
def get_watchlist(user_id: OwnedUserId, db: DbSession, days: int = DEFAULT_DAYS) -> WatchlistOut:
    """The user's watched symbols, ranked by recent momentum (not a forecast)."""
    load_user(db, user_id)
    reports = [
        market_engine.analyze(item.symbol, cache.get_or_fetch(db, item.symbol, days=days))
        for item in market_repo.list_watchlist(db, user_id)
    ]
    db.commit()
    return WatchlistOut(items=market_engine.rank_by_momentum(reports))


@router.post("/market/watchlist/{user_id}", response_model=WatchlistOut,
             status_code=status.HTTP_201_CREATED)
def add_to_watchlist(user_id: OwnedUserId, payload: WatchlistIn, db: DbSession) -> WatchlistOut:
    """Add a symbol. Idempotent — watching something twice is not an error."""
    load_user(db, user_id)
    asset = market_repo.get_asset(db, payload.symbol)
    if asset is None:
        raise HTTPException(
            status_code=422,   # the literal: Starlette renamed this constant, see errors.py
            detail=f"unknown symbol: {payload.symbol}",
        )
    market_repo.add_to_watchlist(db, user_id, asset.symbol)
    db.commit()
    return get_watchlist(user_id, db)


@router.delete("/market/watchlist/{user_id}/{symbol}",
               status_code=status.HTTP_204_NO_CONTENT)
def remove_from_watchlist(user_id: OwnedUserId, symbol: str, db: DbSession) -> Response:
    load_user(db, user_id)
    market_repo.remove_from_watchlist(db, user_id, symbol)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
