"""The one public, unauthenticated market read: recent closes for the assets
the landing page ticks.

It exists so the landing page's sparkline has a shape to draw before the
first live tick arrives. Without it a first-time visitor watches an empty
chart for twenty seconds and then a two-point line, which undercuts the one
section whose job is to prove the product is real.

Two deliberate limits, both of which follow from it being public.

**Cache only, never a provider call.** SPEC section 24 keeps external calls
off the request path, and an unauthenticated route is exactly where that
matters: otherwise anyone could spend the free-tier budget by refreshing. A
cold cache answers with an empty series and the page falls back to
accumulating live ticks, which is the behaviour it had before this route
existed.

**Only the live symbols.** `LIVE_SYMBOLS`, not any symbol in `market_assets`
— the watchlist surface stays behind `require_user`, and this route is not a
way around it.

On provenance: the cache holds whatever filled it, which on a live deployment
is the real provider and in a demo database is the mock one. Nothing here
prints a figure from the series; it is drawn as a line next to a price that
carries its own status, so the shape cannot be mistaken for a quoted number.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.api.deps import DbSession
from app.market import cache
from app.market.live import LIVE_SYMBOLS
from app.schemas.market import MARKET_DISCLAIMER

router = APIRouter(prefix="/api/market/public", tags=["market"])

#: Enough to give the sparkline a readable shape, short enough that a stale
#: snapshot cannot put a month-old line under a live price.
SERIES_DAYS = 14


class PublicPoint(BaseModel):
    date: str
    close: float


class PublicSeriesOut(BaseModel):
    symbol: str
    #: Empty when the cache is cold. A caller renders what it gets and waits
    #: for live ticks; it never interpolates the gap.
    points: list[PublicPoint]
    disclaimer: str = MARKET_DISCLAIMER


@router.get("/{symbol}", response_model=PublicSeriesOut)
def public_series(symbol: str, db: DbSession) -> PublicSeriesOut:
    normalised = symbol.upper()
    if normalised not in LIVE_SYMBOLS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown symbol: {symbol}"
        )
    points = cache.get_cached_series(db, normalised, days=SERIES_DAYS) or []
    return PublicSeriesOut(
        symbol=normalised,
        points=[PublicPoint(date=point.date, close=point.close) for point in points],
    )
