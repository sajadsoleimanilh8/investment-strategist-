"""The public live-price WebSocket (spec: real-time crypto market, no auth).

Deliberately outside `market.router`: every other market route sits behind
`require_user` because it can serve a signed-in user's own watchlist, but a
symbol's current USD price is not personal data, and gating it behind login
would just be friction the public landing page cannot pay.

Public does not mean unguarded. A WebSocket upgrade does not go through CORS
at all — the browser sends the request and the `Origin` header, and nothing
stops a page on another domain from opening a socket here unless this route
checks it. So it does, against the same `CORS_ORIGINS` the HTTP API uses, and
it caps the number of simultaneous connections so one client cannot hold the
process's sockets open indefinitely.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.core.config import settings
from app.market.live import hub

log = logging.getLogger("finmentor.api")

router = APIRouter(prefix="/api/market", tags=["market"])

#: Enough for a normal audience, low enough to be a ceiling. Each connection
#: costs a socket and a slot in the broadcast loop, and the hub polls once for
#: all of them, so this bounds memory rather than provider traffic.
MAX_LIVE_CLIENTS = 200


def origin_allowed(origin: str | None) -> bool:
    """Whether a browser at `origin` may open this socket.

    A missing Origin is allowed: browsers always send one on a WebSocket
    handshake, so a request without it is a server-side client (a test, a
    health probe, `websocat`), and those are not the cross-site risk this
    check exists for. A *present* origin has to be on the list.
    """
    if origin is None:
        return True
    return origin in settings.cors_origins


@router.websocket("/live")
async def market_live(websocket: WebSocket) -> None:
    if not origin_allowed(websocket.headers.get("origin")):
        # Refused before `accept()`, which is what makes it a rejected
        # handshake rather than an accepted-then-dropped connection.
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    if len(hub.clients) >= MAX_LIVE_CLIENTS:
        log.warning("live market socket refused: at capacity (%d)", MAX_LIVE_CLIENTS)
        await websocket.close(code=status.WS_1013_TRY_AGAIN_LATER)
        return

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
