"""Password hashing and token encoding, on their own.

`tests/api/test_auth.py` covers these through HTTP. This file covers the parts
HTTP cannot reach: that a hash is salted, that a token's `typ` is load-bearing,
and that every malformed input produces a `TokenError` rather than a traceback.
"""
import time
from datetime import timedelta

import jwt
import pytest

from app.core import security
from app.core.config import settings


# --- passwords -----------------------------------------------------------

def test_a_password_verifies_against_its_own_hash():
    hashed = security.hash_password("correct horse battery staple")

    assert security.verify_password("correct horse battery staple", hashed)
    assert not security.verify_password("Correct horse battery staple", hashed)


def test_the_same_password_hashes_differently_every_time():
    """Salted. Two users with the same password must not share a hash."""
    first = security.hash_password("same-password-twice")
    second = security.hash_password("same-password-twice")

    assert first != second
    assert security.verify_password("same-password-twice", first)
    assert security.verify_password("same-password-twice", second)


def test_it_is_argon2_and_not_something_older():
    assert security.hash_password("x" * 12).startswith("$argon2id$")


def test_a_long_password_is_not_silently_truncated():
    """bcrypt cuts at 72 bytes, so two different long passwords collide there.
    argon2 does not, and this is the test that would catch a swap back."""
    base = "x" * 80
    hashed = security.hash_password(base + "A")

    assert not security.verify_password(base + "B", hashed)


@pytest.mark.parametrize("stored", [None, "", "not-a-hash", "$argon2id$broken"])
def test_a_missing_or_broken_hash_is_a_failed_login_not_a_crash(stored):
    assert security.verify_password("anything", stored) is False


def test_a_current_hash_does_not_need_rehashing():
    assert security.needs_rehash(security.hash_password("a-fine-password")) is False


def test_an_unreadable_hash_is_treated_as_needing_a_rehash():
    assert security.needs_rehash("not-a-hash") is True


# --- tokens --------------------------------------------------------------

def test_an_access_token_round_trips():
    assert security.decode_token(security.create_access_token(42)) == 42


def test_a_refresh_token_round_trips_when_expected():
    token = security.create_refresh_token(42)

    assert security.decode_token(token, expect=security.REFRESH) == 42


def test_the_kind_is_checked_in_both_directions():
    access = security.create_access_token(1)
    refresh = security.create_refresh_token(1)

    with pytest.raises(security.TokenError):
        security.decode_token(access, expect=security.REFRESH)
    with pytest.raises(security.TokenError):
        security.decode_token(refresh, expect=security.ACCESS)


def test_the_subject_is_a_string_in_the_payload():
    """The JWT spec says `sub` is a string, and PyJWT enforces it on decode."""
    payload = jwt.decode(security.create_access_token(7), settings.jwt_secret,
                         algorithms=["HS256"])

    assert payload["sub"] == "7"
    assert security.decode_token(security.create_access_token(7)) == 7


def test_an_expired_token_raises():
    expired = security._encode(1, security.ACCESS, timedelta(seconds=-10), 0)

    with pytest.raises(security.TokenError, match="expired"):
        security.decode_token(expired)


def test_a_token_signed_with_another_secret_raises(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "another-secret-entirely-long-enough")
    forged = security.create_access_token(1)
    monkeypatch.undo()

    with pytest.raises(security.TokenError):
        security.decode_token(forged)


def test_an_unsigned_token_is_refused():
    """`alg: none` is the oldest JWT attack there is."""
    unsigned = jwt.encode({"sub": "1", "typ": "access"}, key="", algorithm="none")

    with pytest.raises(security.TokenError):
        security.decode_token(unsigned)


@pytest.mark.parametrize("token", ["", "abc", "a.b.c", "...", "null"])
def test_garbage_raises_tokenerror_and_nothing_else(token):
    with pytest.raises(security.TokenError):
        security.decode_token(token)


def test_a_token_with_no_subject_raises():
    payload = jwt.encode({"typ": "access", "exp": int(time.time()) + 60},
                         settings.jwt_secret, algorithm="HS256")

    with pytest.raises(security.TokenError, match="subject"):
        security.decode_token(payload)


def test_the_ttls_come_from_config(monkeypatch):
    monkeypatch.setattr(settings, "access_token_ttl_minutes", 5)
    payload = jwt.decode(security.create_access_token(1), settings.jwt_secret,
                         algorithms=["HS256"])

    assert 4 * 60 <= payload["exp"] - payload["iat"] <= 5 * 60


# --- the bearer header ---------------------------------------------------

def test_a_bearer_header_yields_its_token():
    assert security.bearer_token("Bearer abc.def.ghi") == "abc.def.ghi"


def test_the_scheme_is_matched_case_insensitively():
    assert security.bearer_token("bearer abc") == "abc"


@pytest.mark.parametrize("header", [None, "", "Bearer", "Bearer   ", "Basic abc", "abc"])
def test_anything_else_raises(header):
    with pytest.raises(security.TokenError):
        security.bearer_token(header)


# --- secrets never reach a log ------------------------------------------

def test_a_token_in_a_log_line_is_redacted():
    from app.core.logging import redact

    token = security.create_access_token(1)
    masked = redact(f"authorization: Bearer {token}")

    assert token not in masked


def test_a_password_under_a_password_key_is_redacted():
    from app.core.logging import redact

    assert redact({"password": "hunter2"})["password"] != "hunter2"
