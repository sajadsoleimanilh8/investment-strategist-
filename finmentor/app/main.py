"""FastAPI application factory (spec section 21).
Run: uvicorn app.main:app --reload
"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Request

from app.api.routes import ALL_ROUTERS
from app.core.config import settings
from app.core.logging import configure_logging, safe_json

log = logging.getLogger("finmentor.api")


def _start_scheduler() -> BackgroundScheduler:
    """Warm the market cache on an interval so no request waits on a provider."""
    from scripts.fetch_market_snapshots import main as refresh_snapshots

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        refresh_snapshots,
        "interval",
        seconds=settings.market_cache_ttl_seconds,
        id="market_snapshots",
        max_instances=1,
        coalesce=True,          # a slow run must not queue up duplicates
    )
    scheduler.start()
    log.info("market refresh scheduled every %ss", settings.market_cache_ttl_seconds)
    return scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = _start_scheduler() if settings.enable_scheduler else None
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="FinMentor API", version="0.1.0", lifespan=lifespan)
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

    return app


app = create_app()
