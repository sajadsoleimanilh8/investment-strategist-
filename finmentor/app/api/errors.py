"""One error shape, and nothing behind it that a caller should not see.

Every failure the API can produce leaves through here, so a client has exactly
one body to parse:

    {"error": {"code": "not_found", "message": "...", "request_id": "..."}}

Three rules the handlers exist to enforce:

* **A 500 says nothing about why.** An unhandled exception is, by definition,
  one nobody anticipated — its message may contain a connection string, a
  token, or a row of someone's financial data. The client gets a fixed
  sentence and a request id; the detail goes to the log, scrubbed.
* **A 4xx says exactly why**, because the caller can act on it. Those messages
  are written by us, not by an exception.
* **The request id is the join.** It is in the response, in the log line, and
  in the `X-Request-ID` header, so a user can quote eight characters and have
  someone find the exact failure.
"""
from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import redact, scrub_text

log = logging.getLogger("finmentor.api")

#: What a 500 tells the user. Deliberately incurious: the alternative is
#: leaking whatever the exception happened to be carrying.
UNEXPECTED = "Something went wrong on our side. Try again in a moment."

#: HTTP status -> the stable code a client can branch on without parsing prose.
CODES = {
    400: "bad_request",
    401: "unauthenticated",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "invalid_request",
    429: "rate_limited",
    500: "internal_error",
    503: "unavailable",
}


def request_id(request: Request) -> str:
    """Short, per-request, and stable across the log line and the response."""
    existing = getattr(request.state, "request_id", None)
    if existing:
        return existing
    generated = uuid.uuid4().hex[:8]
    request.state.request_id = generated
    return generated


def error_body(status_code: int, message: str, rid: str, **extra) -> dict:
    body = {
        "error": {
            "code": CODES.get(status_code, "error"),
            "message": message,
            "request_id": rid,
        }
    }
    if extra:
        body["error"].update(extra)
    return body


def install(app: FastAPI) -> None:
    """Attach the handlers. Called once, from the app factory."""

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        """A raised HTTPException: the message is ours, so it is safe to send.

        Scrubbed anyway. `detail` is occasionally built from a value that came
        in with the request, and that is exactly the path by which a secret
        ends up echoed back.
        """
        rid = request_id(request)
        message = scrub_text(str(exc.detail))
        if exc.status_code >= 500:
            log.error("%s %s -> %s [%s] %s", request.method, request.url.path,
                      exc.status_code, rid, message)
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(exc.status_code, message, rid),
            headers={**(exc.headers or {}), "X-Request-ID": rid},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        """422 with the field-level detail a form needs to show inline.

        Pydantic's raw errors carry the rejected `input` back, which for a
        signup is the password. The field location and the reason survive; the
        value never does.
        """
        rid = request_id(request)
        fields = [
            {
                "field": ".".join(str(part) for part in error["loc"][1:]) or "body",
                "message": scrub_text(str(error.get("msg", "is not valid"))),
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=error_body(422, "Some of that was not valid.", rid, fields=fields),
            headers={"X-Request-ID": rid},
        )

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        """The one nobody planned for.

        `log.exception` keeps the traceback server-side; the type and message
        are scrubbed before they reach even the log, because a DSN in a
        connection error is a credential wherever it is written.
        """
        rid = request_id(request)
        log.exception(
            "unhandled %s on %s %s [%s]: %s",
            type(exc).__name__, request.method, request.url.path, rid,
            redact(str(exc)),
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_body(500, UNEXPECTED, rid),
            headers={"X-Request-ID": rid},
        )
