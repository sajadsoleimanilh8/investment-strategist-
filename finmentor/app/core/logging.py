"""Structured logging setup.

Spec section 26: never log keys, tokens, or financial PII. Anything that could
carry a request/response body must pass through `redact()` first — the request
middleware in `app.main` logs metadata only, and `redact()` is what makes the
remaining call sites (scripts, debug logs) safe.
"""
from __future__ import annotations

import contextvars
import json
import logging
import re
from typing import Any

from app.core.config import settings

#: The id of the request being served on this task, or "-" outside one.
#:
#: A context variable rather than a parameter threaded through every call: the
#: point is that log lines nobody wrote for observability -- the limiter's
#: warning that Redis is unreachable, the AI layer's timing, a driver's
#: complaint -- come out carrying the request they happened in. Threading an
#: argument would only correlate the call sites that remembered to.
#:
#: It is a `ContextVar`, so a request handler and anything it awaits share a
#: value while two concurrent requests do not. `asyncio.to_thread` copies the
#: context, so the bot's and the API's worker threads inherit it too.
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "finmentor_request_id", default="-"
)

#: substrings that mark a key as a credential
_SECRET_KEY_PARTS = (
    "token", "api_key", "apikey", "authorization", "password", "secret",
    "credential", "cookie", "session_id",
)

#: keys whose *values* are raw financial figures
_FINANCIAL_KEYS = frozenset({
    "monthly_income", "income", "current_savings", "savings", "debt",
    "monthly_debt_payment", "emergency_fund", "amount", "target_amount",
    "current_amount", "monthly_expenses", "monthly_savings", "balance",
    "essential_monthly_expenses", "net_worth", "price", "total",
})

#: keys whose whole subtree is financial figures (category breakdowns etc.)
_FINANCIAL_CONTAINERS = frozenset({"expenses", "planned_budget", "breakdown", "allocation"})

#: keys whose *values* are direct identifiers
_PII_KEYS = frozenset({"telegram_id", "phone", "email", "username", "first_name", "last_name"})

SECRET_MASK = "***"
AMOUNT_MASK = "<amount>"
ID_MASK = "<id>"

_MAX_DEPTH = 6

#: Credentials that arrive inside free text rather than under a key — the
#: password in a connection string, or a bearer token in an exception message.
#: `redact` is key-driven, so a bare string used to sail straight through it,
#: which is how a DSN can end up in a log line from an error handler.
_DSN_CREDENTIALS = re.compile(r"(?<=://)([^\s:/@]+):([^\s:/@]+)(?=@)")
_LABELLED_SECRET = re.compile(
    r"\b(bearer|token|api[_-]?key)(\s*[:=]\s*|\s+)(\S+)", re.IGNORECASE
)
_TELEGRAM_TOKEN = re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{30,}\b")
#: A Telegram link code, in either form it travels in: `ABCD-EFGH-JKMN` off a
#: web page, or `link_ABCDEFGHJKMN` inside a deep link. Unlike the two above
#: it is not labelled, so nothing key-driven would ever find it.
#:
#: No code reaches a log through this codebase: the refusals in
#: `app/api/telegram_link.py` never repeat the code back, which is the actual
#: control. This is the second line, for the paths that are not ours -- PTB
#: logging an update, or a driver quoting the parameters of a failed
#: statement. The alphabet is `LINK_CODE_ALPHABET`, narrow enough that a false
#: positive has to be twelve characters of exactly those symbols.
_LINK_CODE = re.compile(
    r"\b(?:link_)?[2-9A-HJ-NP-TW-Z]{4}-?[2-9A-HJ-NP-TW-Z]{4}-?[2-9A-HJ-NP-TW-Z]{4}\b"
)


def scrub_text(text: str) -> str:
    """Mask credentials embedded in an arbitrary string.

    For messages we did not build ourselves — exception text above all, which
    routinely quotes the connection string that failed. The username survives
    (it is useful in a log); only the secret half is masked.
    """
    text = _DSN_CREDENTIALS.sub(rf"\1:{SECRET_MASK}", text)
    text = _LABELLED_SECRET.sub(rf"\1\2{SECRET_MASK}", text)
    text = _TELEGRAM_TOKEN.sub(SECRET_MASK, text)
    return _LINK_CODE.sub(SECRET_MASK, text)


def install_record_factory() -> None:
    """Stamp `request_id` onto every record at the moment it is created.

    A record factory rather than a `logging.Filter`, and the difference
    matters. A filter lives on a handler, so it only reaches records that
    reach *that* handler: anything added later -- another handler, pytest's
    capture, a sidecar that ships logs somewhere -- sees records without the
    field. A filter on a logger is worse still, because logger-level filters
    are not applied to records propagated up from child loggers, which is
    almost all of them.

    The factory runs before any of that, so the field is simply part of every
    record. Idempotent via the marker, because `configure_logging` is called
    by the API, the bot and a number of tests.
    """
    base = logging.getLogRecordFactory()
    if getattr(base, "_finmentor_request_id", False):
        return

    def factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
        record = base(*args, **kwargs)
        if not hasattr(record, "request_id"):
            record.request_id = request_id_var.get()
        return record

    factory._finmentor_request_id = True  # type: ignore[attr-defined]
    logging.setLogRecordFactory(factory)


#: Attributes `logging` puts on every record. Anything else a caller passed
#: through `extra=` is ours and belongs in the JSON output.
_STANDARD_RECORD_ATTRS = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__
) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    """One JSON object per line, for a log that is queried rather than read.

    The message stays human-readable alongside the fields rather than being
    replaced by them: a formatted sentence is what makes a log line legible
    when somebody is tailing it, and the fields are what make it searchable.
    Both are cheap.

    Every string value goes through `scrub_text`, including the message. A
    structured log is not a safer log by itself -- it is a log that puts
    whatever it was handed into a field instead of a sentence -- and the
    redaction rules are the same rules either way.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": scrub_text(record.getMessage()),
            "request_id": getattr(record, "request_id", request_id_var.get()),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_RECORD_ATTRS and key != "request_id":
                payload[key] = redact(value)
        if record.exc_info:
            payload["exception"] = scrub_text(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


#: `text` is readable while you are looking at it; `json` is queryable after
#: the fact. The default is text because that is what a developer running
#: `uvicorn` wants, and the compose file sets json because that is what a
#: deployment wants. Neither is a better default in the abstract.
LOG_FORMATS = ("text", "json")
TEXT_FORMAT = "%(asctime)s %(levelname)s %(name)s [%(request_id)s] :: %(message)s"


def configure_logging() -> None:
    """Install the handler, the formatter and the request-id filter.

    Idempotent: `configure_logging` is called by the API factory, by the bot
    and by several tests, and `basicConfig` is a no-op once a handler exists
    -- which used to mean the second caller silently got the first one's
    format. This replaces the handler's formatter instead of trusting that.
    """
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    wanted = settings.log_format.lower()
    if wanted not in LOG_FORMATS:
        wanted = "text"

    formatter: logging.Formatter = (
        JsonFormatter() if wanted == "json" else logging.Formatter(TEXT_FORMAT)
    )

    install_record_factory()

    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(level=level)
    root.setLevel(level)
    for handler in root.handlers:
        handler.setFormatter(formatter)


def _is_secret(key: str) -> bool:
    lowered = key.lower()
    return any(part in lowered for part in _SECRET_KEY_PARTS)


def _is_financial(key: str) -> bool:
    lowered = key.lower()
    return lowered in _FINANCIAL_KEYS or lowered.endswith(("_amount", "_income", "_savings"))


def redact(data: Any, _depth: int = 0, _in_financial: bool = False) -> Any:
    """Recursively mask credentials, identifiers, and raw financial figures.

    Structure is preserved so a redacted payload is still useful for debugging;
    only the sensitive leaves are replaced.
    """
    if _depth > _MAX_DEPTH:
        return "<truncated>"
    if _in_financial and not isinstance(data, (dict, list, tuple, bool)) and data is not None:
        return AMOUNT_MASK
    if isinstance(data, str):
        return scrub_text(data)
    if isinstance(data, dict):
        out: dict[Any, Any] = {}
        for key, value in data.items():
            name = str(key)
            if _is_secret(name):
                out[key] = SECRET_MASK
            elif name.lower() in _PII_KEYS:
                out[key] = ID_MASK
            elif _is_financial(name) or name.lower() in _FINANCIAL_CONTAINERS:
                # a figure, or a container of figures — either way, mask the leaves
                out[key] = redact(value, _depth + 1, _in_financial=True)
            else:
                out[key] = redact(value, _depth + 1, _in_financial=_in_financial)
        return out
    if isinstance(data, (list, tuple)):
        return [redact(item, _depth + 1, _in_financial=_in_financial) for item in data]
    return data


def safe_json(data: Any) -> str:
    """`redact()` + `json.dumps` — the only sanctioned way to log a payload."""
    return json.dumps(redact(data), ensure_ascii=False, default=str)
