"""The public live-price WebSocket (spec: real-time crypto market, no auth).

Deliberately outside `market.router`: every other market route sits behind
`require_user` because it can serve a signed-in user's own watchlist, but a
symbol's current USD price is not personal data — gating it behind login
would just be friction, and the public landing page needs it un-authenticated.
"""
from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.market.live import hub

router = APIRouter(prefix="/api/market", tags=["market"])


@router.websocket("/live")
async def market_live(websocket: WebSocket) -> None:
    await hub.register(websocket)
    try:
        while True:
            # The client sends nothing; this just blocks until it disconnects
            # (or drops), which is the only thing this loop needs to detect.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        hub.unregister(websocket)
