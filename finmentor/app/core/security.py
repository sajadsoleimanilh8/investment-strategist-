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

import base64
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import settings

ALGORITHM = "HS256"
ACCESS = "access"
REFRESH = "refresh"
#: Two more short-lived kinds, both for third-party sign-in. `state` is the
#: round trip to a provider; `handoff` is the moment between the provider
#: sending the browser back and the frontend asking for its tokens. Both carry
#: `typ` and are checked for it, for the same reason access and refresh are:
#: a token accepted in the wrong place is a longer session than intended.
STATE = "oauth_state"
HANDOFF = "oauth_handoff"

#: argon2id at the library's defaults — a deliberate choice over bcrypt, which
#: silently truncates at 72 bytes and is cheaper to attack on a GPU.
_hasher = PasswordHasher()


class TokenError(Exception):
    """A token that is missing, malformed, expired, or of the wrong kind."""


# --- passwords -----------------------------------------------------------

def hash_password(password: str) -> str:
    return _hasher.hash(password)


#: A real argon2 hash of a value nobody holds, verified against when there is
#: no stored hash to verify against. Computed once at import, because the cost
#: that matters is the *verify*, not the hash.
#:
#: Without it, `verify_password` returned False immediately for an unknown
#: email and spent ~50ms hashing for a known one, and that difference is
#: readable over the network. The login route says in its own constant that
#: telling the two apart "hands an attacker a free account-existence oracle";
#: answering with the same sentence at a measurably different speed hands over
#: the same thing more slowly.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(32))


def verify_password(password: str, password_hash: str | None) -> bool:
    """Constant-ish time check. A user with no password never verifies.

    Telegram-only accounts have `password_hash = None`, and an unknown email
    has no row at all. Both still pay for one argon2 verification against
    `_DUMMY_HASH`, so the answer takes the same time as a real wrong password.
    Returning False rather than raising means "wrong credentials", which is
    what it is.

    This is not perfect constant time and does not pretend to be: argon2's own
    runtime varies a little, and so does the network. It removes the
    difference an attacker can actually measure, which is the whole 50ms gap
    between "no such account" and "wrong password".
    """
    if not password_hash:
        try:
            _hasher.verify(_DUMMY_HASH, password)
        except (VerificationError, InvalidHashError):
            pass
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

def _encode(subject: int, kind: str, lifetime: timedelta, version: int) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": str(subject),        # a string: the JWT spec says so, and PyJWT enforces it
        "typ": kind,
        "ver": version,             # `users.token_version` when this was minted
        "iat": int(now.timestamp()),
        "exp": int((now + lifetime).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=ALGORITHM)


def create_access_token(user_id: int, version: int = 0) -> str:
    return _encode(user_id, ACCESS,
                   timedelta(minutes=settings.access_token_ttl_minutes), version)


def create_refresh_token(user_id: int, version: int = 0) -> str:
    return _encode(user_id, REFRESH,
                   timedelta(days=settings.refresh_token_ttl_days), version)


@dataclass(frozen=True)
class TokenClaims:
    user_id: int
    #: When this token was signed. Informational: the guard compares `version`,
    #: not this, because `iat` is whole seconds and that is too coarse to
    #: separate a reset from a session started in the same second as it.
    issued_at: datetime
    #: `users.token_version` at the moment of minting. A token whose version no
    #: longer matches the user's is refused. Absent on tokens issued before
    #: this claim existed, which read as 0 — the value every account starts
    #: at, so the upgrade itself signs nobody out.
    version: int = 0


def decode_claims(token: str, *, expect: str = ACCESS) -> TokenClaims:
    """The claims inside a valid token of the expected kind.

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
        user_id = int(payload["sub"])
        issued_at = datetime.fromtimestamp(int(payload["iat"]), tz=timezone.utc)
        version = int(payload.get("ver", 0))
    except (KeyError, TypeError, ValueError, OSError, OverflowError) as exc:
        raise TokenError("token has no usable subject") from exc
    return TokenClaims(user_id=user_id, issued_at=issued_at, version=version)


def decode_token(token: str, *, expect: str = ACCESS) -> int:
    """Just the user id. The shape most callers want."""
    return decode_claims(token, expect=expect).user_id


# --- reset tokens --------------------------------------------------------

#: Long enough that guessing is hopeless, short enough to survive an email
#: client wrapping the line. `token_urlsafe(32)` is 256 bits.
RESET_TOKEN_BYTES = 32


def new_reset_token() -> tuple[str, str]:
    """A reset token and the hash to store: `(raw, hashed)`.

    Deliberately not a JWT. A reset has to be single-use, and single-use means
    the server has to remember whether it was spent — which a stateless token
    cannot do. Once there is a row anyway, the row may as well be the whole
    mechanism.
    """
    raw = secrets.token_urlsafe(RESET_TOKEN_BYTES)
    return raw, hash_reset_token(raw)


def hash_reset_token(raw: str) -> str:
    """SHA-256, not argon2.

    Password hashing is deliberately slow because a password is short, human
    and often reused. A 256-bit random token is none of those: there is no
    dictionary to run against it, so the only thing an expensive hash would
    add here is a lookup slow enough to be a denial-of-service lever.
    """
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


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


# --- short-lived signed payloads ----------------------------------------

def sign_payload(payload: dict[str, Any], *, kind: str, lifetime: timedelta) -> str:
    """A signed, expiring blob for a round trip through someone else's site.

    Used for the OAuth `state` parameter, which has to survive a redirect to a
    provider and back without this app storing anything. Signing it is what
    makes that safe: a state the server did not mint will not verify, which is
    the whole defence against a callback nobody here started.
    """
    now = datetime.now(timezone.utc)
    body = dict(payload)
    body.update({
        "typ": kind,
        "iat": int(now.timestamp()),
        "exp": int((now + lifetime).timestamp()),
    })
    return jwt.encode(body, settings.jwt_secret, algorithm=ALGORITHM)


def read_payload(token: str, *, kind: str) -> dict[str, Any]:
    """The payload back, or `TokenError`."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("that sign-in attempt has expired") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("that sign-in attempt is not valid") from exc
    if payload.get("typ") != kind:
        raise TokenError(f"expected a {kind} token")
    return payload


def pkce_pair() -> tuple[str, str]:
    """A PKCE verifier and its S256 challenge.

    Proof that the app finishing the flow is the one that started it. Without
    it, an authorization code intercepted on the way back (a shared machine's
    history, a leaky redirect) can be spent by whoever holds it.
    """
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge
