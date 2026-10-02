"""FastAPI application factory (spec section 21).
Run: uvicorn app.main:app --reload
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from contextlib import asynccontextmanager

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import errors
from app.api.routes import ALL_ROUTERS
from app.core import leader
from app.core.config import settings
from app.core.logging import (
    configure_logging, request_id_var, safe_json, scrub_text,
)
from app.market.live import hub as market_live_hub

log = logging.getLogger("finmentor.api")

#: The shape `request_id` is generated in: eight lower-case hex characters.
#: A client may supply its own to stitch a trace together, and anything that
#: is not this shape is replaced rather than trusted.
_REQUEST_ID = re.compile(r"[0-9a-f]{8}")

#: The biggest request body any route legitimately needs. The largest is a
#: full financial profile: nine numbers, a risk profile and two expense
#: breakdowns, which is a few hundred bytes. 64 KiB leaves room for a
#: future field without leaving room for an upload.
MAX_BODY_BYTES = 64 * 1024


def _start_scheduler() -> BackgroundScheduler:
    """The background jobs: warm the market cache, and keep three tables bounded.

    Two things here are not obvious from the calls.

    The refresh interval is a *fraction* of the cache TTL, never the TTL
    itself. Scheduling it at exactly the freshness window guarantees a gap:
    the snapshot expires at the same moment its replacement is due, so every
    cycle had a stretch where requests fell through to a provider, which is
    the thing SPEC section 24 says must not happen once warm.

    Both jobs run behind a lease, so a deployment with several replicas does
    the work once rather than once per container. Without Redis every replica
    runs, which is right for the single-container deployment this project
    ships: duplicated work is a cost, no work at all is an outage.
    """
    from scripts.fetch_market_snapshots import main as refresh_snapshots
    from scripts.prune_records import main as prune_records

    scheduler = BackgroundScheduler()
    scheduler.add_job(
        lambda: leader.run_if_leader("market_snapshots", refresh_snapshots),
        "interval",
        seconds=settings.market_refresh_interval_seconds,
        id="market_snapshots",
        max_instances=1,
        coalesce=True,          # a slow run must not queue up duplicates
    )
    scheduler.add_job(
        lambda: leader.run_if_leader("retention", prune_records),
        "interval",
        seconds=settings.retention_interval_seconds,
        id="retention",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    log.info(
        "scheduled: market refresh every %ss (cache ttl %ss), retention every %ss",
        settings.market_refresh_interval_seconds,
        settings.market_cache_ttl_seconds,
        settings.retention_interval_seconds,
    )
    return scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = _start_scheduler() if settings.enable_scheduler else None
    # `start` is a no-op when MARKET_LIVE_SOURCE resolves to off, so the
    # decision stays in one place (config) instead of being half here.
    market_live_hub.start()
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)
        await market_live_hub.stop()


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="FinMentor API", version="0.1.0", lifespan=lifespan)
    # The browser client is a separate origin from the API. Credentials are
    # bearer tokens in a header, not cookies, so this needs no
    # `allow_credentials` — and origins stay an explicit list, never "*".
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )

    # Before the routers: a handler registered later still catches everything,
    # but keeping it here makes the order of the pipeline readable.
    errors.install(app)

    for router in ALL_ROUTERS:
        app.include_router(router)

    @app.middleware("http")
    async def limit_body_size(request: Request, call_next):
        """Refuse an oversized body before anything reads it.

        The schemas cap individual fields, but a field cap only applies once
        the body has been received and parsed — which is the expensive part.
        This is the ceiling on the whole request, and it lives here rather
        than only in nginx because nginx fronts the *web bundle*: in the
        compose topology the browser calls the API directly, so a proxy limit
        would not be on this path at all. Deployments that do put a proxy in
        front get the same limit twice, which is the right number.

        `Content-Length` only: a chunked upload has none, and Starlette's own
        body reader is what bounds those. This is the cheap check that stops
        the common case at the door.
        """
        declared = request.headers.get("content-length")
        if declared is not None and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
            return JSONResponse(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content={"error": {
                    "code": "payload_too_large",
                    "message": "That request is too large.",
                    "request_id": errors.request_id(request),
                }},
            )
        return await call_next(request)

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        """Access log. Bodies are never read here; query params are redacted.

        Three things happen before `call_next`, and the order is the point:
        the request gets an id, that id goes into the context, and only then
        is anything else allowed to log. A line emitted by the limiter or the
        AI layer halfway through the request carries the id because of this,
        not because those call sites know about it.

        The id reaches the client on every response, not only on errors. It
        was already on the three error bodies, which is the half of the
        problem you notice; the other half is a user describing a request that
        *worked* and nobody being able to find it.
        """
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:8]
        # A client-supplied id is free-form input that will be written to a log
        # and echoed in a header: keep only the shape we generate ourselves.
        if not _REQUEST_ID.fullmatch(rid):
            rid = uuid.uuid4().hex[:8]
        request.state.request_id = rid
        token = request_id_var.set(rid)

        started = time.perf_counter()
        try:
            response = await call_next(request)
        except BaseException:
            request_id_var.reset(token)
            raise
        elapsed_ms = (time.perf_counter() - started) * 1000

        # The matched route's template, not the path that was typed. Logging
        # `/api/goals/7` makes every record its own distinct key -- the thing
        # that turns an access log into an unqueryable pile -- and writes a
        # record id into the log on the way. `route` is on the scope once
        # routing has run, which is why this reads it after `call_next`.
        route = request.scope.get("route")
        template = getattr(route, "path", None) or scrub_text(request.url.path)

        params = dict(request.query_params)
        log.info(
            "%s %s -> %s in %.1fms%s",
            request.method, template, response.status_code, elapsed_ms,
            f" params={safe_json(params)}" if params else "",
            extra={
                "event": "http_request",
                "method": request.method,
                "route": template,
                "status": response.status_code,
                "duration_ms": round(elapsed_ms, 1),
                # The caller, when there is one. Without it the operational
                # question "what did this person actually experience" has no
                # answer. It does make the access log personal data, which is
                # noted against the retention decision in PROJECT_STATE.
                "user_id": getattr(request.state, "user_id", None),
                # `request_id` is deliberately *not* passed here. The record
                # factory has already set it, and `logging` raises on an
                # `extra` key that would overwrite an existing attribute --
                # which is why the context variable is reset after this call
                # rather than before it.
            },
        )
        response.headers["X-Request-ID"] = rid
        request_id_var.reset(token)
        return response

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok", "demo_mode": settings.demo_mode}

    return app


app = create_app()
