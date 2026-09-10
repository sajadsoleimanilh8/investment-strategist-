"""Password hashing, JWTs, and rate-limit keys.

Two identities reach the same rows. A Telegram user is known by their
`telegram_id` and never authenticates — the bot resolves them from the update
and calls the pipeline in-process. A web user authenticates with an email and
a password and carries a bearer token. One `users` row can hold both.

Nothing here touches the database or FastAPI: this is the crypto and the token
format, and `app/api/deps.py` is where a token becomes a `User`.

Token design:

* **access** — 30 minutes, sent on every request. Short because it cannot be
  revoked: the only thing standing between a leaked access token and an
  attacker is its expiry.
* **refresh** — 14 days, sent only to `/api/auth/refresh`, and rotated on every
  use so a stolen refresh token stops working the moment the real user refreshes.
* `typ` distinguishes them, and is checked. Without it a refresh token would be
  accepted as an access token, which would quietly make every session
  fourteen days long.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import settings

ALGORITHM = "HS256"
ACCESS = "access"
REFRESH = "refresh"

#: argon2id at the library's defaults — a deliberate choice over bcrypt, which
#: silently truncates at 72 bytes and is cheaper to attack on a GPU.
_hasher = PasswordHasher()


class TokenError(Exception):
    """A token that is missing, malformed, expired, or of the wrong kind."""


# --- passwords -----------------------------------------------------------

def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Constant-ish time check. A user with no password never verifies.

    Telegram-only accounts have `password_hash = None`; returning False rather
    than raising means "wrong credentials", which is what it is.
    """
    if not password_hash:
        return False
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """True when the stored hash predates the current argon2 parameters."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except InvalidHashError:
        return True


# --- tokens --------------------------------------------------------------

def _encode(subject: int, kind: str, lifetime: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(subject),        # a string: the JWT spec says so, and PyJWT enforces it
        "typ": kind,
        "iat": int(now.timestamp()),
        "exp": int((now + lifetime).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def create_access_token(user_id: int) -> str:
    return _encode(user_id, ACCESS, timedelta(minutes=settings.access_token_ttl_minutes))


def create_refresh_token(user_id: int) -> str:
    return _encode(user_id, REFRESH, timedelta(days=settings.refresh_token_ttl_days))


def decode_token(token: str, *, expect: str = ACCESS) -> int:
    """The user id inside a valid token of the expected kind.

    Raises `TokenError` for anything else — expired, tampered, wrong secret, or
    a refresh token presented where an access token belongs.
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("token has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("token is not valid") from exc

    if payload.get("typ") != expect:
        raise TokenError(f"expected a {expect} token")
    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TokenError("token has no usable subject") from exc


def bearer_token(authorization: str | None) -> str:
    """The token out of an `Authorization: Bearer <token>` header."""
    if not authorization:
        raise TokenError("no authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise TokenError("authorization header is not a bearer token")
    return token.strip()


# --- rate limiting -------------------------------------------------------

def rate_limit_key(user_id: str, bucket: str) -> str:
    return f"rl:{bucket}:{user_id}"
