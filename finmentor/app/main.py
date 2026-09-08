"""FastAPI application factory (spec section 21).
Run: uvicorn app.main:app --reload
"""
from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request

from app.api.routes import ALL_ROUTERS
from app.core.config import settings
from app.core.logging import configure_logging, safe_json

log = logging.getLogger("finmentor.api")


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="FinMentor API", version="0.1.0")
    for router in ALL_ROUTERS:
        app.include_router(router)

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        """Access log. Bodies are never read here; query params are redacted."""
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        params = dict(request.query_params)
        log.info(
            "%s %s -> %s in %.1fms%s",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
            f" params={safe_json(params)}" if params else "",
        )
        return response

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok", "demo_mode": settings.demo_mode}

    # TODO(phase-4): APScheduler lifespan job to warm the market cache.
    return app


app = create_app()
