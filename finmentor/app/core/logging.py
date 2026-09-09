"""Structured logging setup.

Spec section 26: never log keys, tokens, or financial PII. Anything that could
carry a request/response body must pass through `redact()` first — the request
middleware in `app.main` logs metadata only, and `redact()` is what makes the
remaining call sites (scripts, debug logs) safe.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.core.config import settings

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


def scrub_text(text: str) -> str:
    """Mask credentials embedded in an arbitrary string.

    For messages we did not build ourselves — exception text above all, which
    routinely quotes the connection string that failed. The username survives
    (it is useful in a log); only the secret half is masked.
    """
    text = _DSN_CREDENTIALS.sub(rf"\1:{SECRET_MASK}", text)
    text = _LABELLED_SECRET.sub(rf"\1\2{SECRET_MASK}", text)
    return _TELEGRAM_TOKEN.sub(SECRET_MASK, text)


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s :: %(message)s",
    )


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
