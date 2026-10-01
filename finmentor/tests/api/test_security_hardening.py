"""Four disclosures and a replay, none of which showed up in a response body.

* `login` and `forgot-password` both answer the same sentence whether or not
  an address is registered, and both took a measurably different amount of
  time to say it. The constants in `auth.py` name that exact attack as the
  thing they prevent.
* The OAuth handoff token was signed, stateless and single-use by intention
  only: `exchange` cleared the cookie and left the token valid for its full
  sixty seconds.
* `_safe_next` rejected `//evil.com` and accepted `/\\evil.com`, which
  browsers resolve to the same place.

Timing is asserted structurally rather than with a stopwatch. A clock-based
test on a shared runner is a coin flip, and what actually needs to be true is
that the expensive work happens on both branches — so that is what these
check.
"""
from __future__ import annotations

import pytest

from app.api.routes.oauth import _safe_next
from app.core import nonce, security

PASSWORD = "a-long-enough-password"


# --- S3: the account-existence oracle ------------------------------------

class _CountingHasher:
    """Wraps the real hasher and records what it was asked to verify.

    A proxy rather than `monkeypatch.setattr(hasher, "verify", ...)`:
    argon2's `PasswordHasher.verify` is read-only on the instance.
    """

    def __init__(self, real):
        self.real = real
        self.verified: list[str] = []

    def verify(self, stored, password):
        self.verified.append(stored)
        return self.real.verify(stored, password)

    def hash(self, password):
        return self.real.hash(password)

    def check_needs_rehash(self, stored):
        return self.real.check_needs_rehash(stored)


def test_an_unknown_address_still_costs_an_argon2_verification(monkeypatch):
    """The whole 50ms gap, in one assertion.

    `verify_password` returned False immediately when there was no stored
    hash, so an unknown email answered far faster than a wrong password.
    """
    counting = _CountingHasher(security._hasher)
    monkeypatch.setattr(security, "_hasher", counting)

    assert security.verify_password(PASSWORD, None) is False

    assert len(counting.verified) == 1, "no hash was verified for a missing password"
    assert counting.verified[0] == security._DUMMY_HASH


def test_the_dummy_hash_is_a_real_argon2_hash():
    """A cheap stand-in would not close the gap it exists to close."""
    assert security._DUMMY_HASH.startswith("$argon2")


def test_nobody_can_sign_in_with_the_dummy_hash(db):
    """It is a hash of a value nobody holds, not a backdoor."""
    assert security.verify_password(security._DUMMY_HASH, None) is False
    assert security.verify_password("", None) is False


def test_login_verifies_a_password_even_for_an_unknown_address(raw_client, monkeypatch):
    """Written the obvious way, Python short-circuits and never verifies.

    `user is None or not verify(...)` skips the expensive half for exactly
    the case the timing attack probes, which is why the route calls
    `verify_password` before it tests `user is None`.
    """
    calls = []
    original = security.verify_password

    def counting(password, stored):
        calls.append(stored)
        return original(password, stored)

    monkeypatch.setattr("app.api.routes.auth.security.verify_password", counting)

    response = raw_client.post("/api/auth/login",
                               json={"email": "nobody@example.com", "password": PASSWORD})

    assert response.status_code == 401
    assert calls == [None], "the route skipped the hash for an unknown address"


def test_both_login_failures_say_the_same_thing(raw_client):
    """The message half of the same defence, asserted alongside the timing."""
    raw_client.post("/api/auth/signup",
                    json={"email": "known@example.com", "password": PASSWORD})

    unknown = raw_client.post("/api/auth/login",
                              json={"email": "nobody@example.com", "password": PASSWORD})
    wrong = raw_client.post("/api/auth/login",
                            json={"email": "known@example.com", "password": "wrong-one-here"})

    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["error"]["message"] == wrong.json()["error"]["message"]


def test_the_reset_email_is_sent_after_the_response(raw_client, monkeypatch):
    """SMTP was on the request path, with a ten-second timeout.

    That made a registered address take up to ten seconds and an
    unregistered one take none, which is the same disclosure the route's
    single sentence exists to prevent, read off the clock. Asserted by
    proving the send is queued as a background task rather than called
    inline.
    """
    raw_client.post("/api/auth/signup",
                    json={"email": "resetme@example.com", "password": PASSWORD})

    sent_during_request = []
    monkeypatch.setattr("app.api.routes.auth.send_quietly",
                        lambda message: sent_during_request.append(message))

    response = raw_client.post("/api/auth/forgot-password",
                               json={"email": "resetme@example.com"})

    assert response.status_code == 202
    # TestClient runs background tasks as part of the request, so this fires
    # either way; what it proves is that the route hands `send_quietly` to
    # the background rather than awaiting it before returning.
    import inspect

    from app.api.routes import auth

    source = inspect.getsource(auth.forgot_password)
    assert "background.add_task" in source
    assert "send_quietly(Message(" not in source, "the send is still inline"


def test_forgot_password_answers_the_same_for_both(raw_client):
    raw_client.post("/api/auth/signup",
                    json={"email": "real@example.com", "password": PASSWORD})

    known = raw_client.post("/api/auth/forgot-password", json={"email": "real@example.com"})
    unknown = raw_client.post("/api/auth/forgot-password", json={"email": "no@example.com"})

    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()


# --- S4: the redirect guard, on both sides -------------------------------

#: Shared with `web/src/auth/safeNext.test.ts`. A guard that holds on one
#: side only is not a guard, so the two tables are kept identical by hand and
#: this comment is the reminder to change both.
SAFE_NEXT_CASES = [
    ("/dashboard", "/dashboard"),
    ("/goals", "/goals"),
    ("/learn?topic=budgeting", "/learn?topic=budgeting"),
    ("/", "/"),
    # Protocol-relative: starts with a slash, resolves to another host.
    ("//evil.com", "/dashboard"),
    ("///evil.com", "/dashboard"),
    # Browsers normalise a backslash to a slash in the authority position, so
    # this is `//evil.com` by the time it is resolved. The original check for
    # "does not start with //" let it straight through.
    (r"/\evil.com", "/dashboard"),
    (r"/\/evil.com", "/dashboard"),
    # Absolute URLs.
    ("https://evil.com", "/dashboard"),
    ("http://evil.com", "/dashboard"),
    ("javascript:alert(1)", "/dashboard"),
    # Characters the browser strips before resolving, which turns these into
    # the protocol-relative cases above *after* any naive check has run.
    ("/\t/evil.com", "/dashboard"),
    ("/\n/evil.com", "/dashboard"),
    ("/\r/evil.com", "/dashboard"),
    # Not a path at all.
    ("", "/dashboard"),
    ("dashboard", "/dashboard"),
]


@pytest.mark.parametrize("given,expected", SAFE_NEXT_CASES,
                         ids=[repr(case[0]) for case in SAFE_NEXT_CASES])
def test_the_server_redirect_guard(given, expected):
    assert _safe_next(given) == expected


def test_the_client_guard_has_the_same_cases():
    """The two tables must not drift.

    The client's copy of this rule is the only thing standing between a
    crafted `/auth/callback?next=//evil.com` and a redirect off-site, because
    that page reads `next` from its own query string rather than from the
    signed state.
    """
    import pathlib

    client = (pathlib.Path(__file__).resolve().parents[2]
              / "web" / "src" / "auth" / "safeNext.test.ts")
    assert client.exists(), "the client guard has no test"

    source = client.read_text(encoding="utf-8")
    for given, _ in SAFE_NEXT_CASES:
        if not given or any(character in given for character in "\t\r\n"):
            continue                       # spelled out by name in the TS file
        # A backslash is written escaped inside a TypeScript string literal,
        # so compare against what the source actually spells.
        needle = given.replace("\\", "\\\\")
        assert needle in source, f"the client table is missing {given!r}"


# --- S5: the handoff is spendable once -----------------------------------

@pytest.fixture
def spendable(monkeypatch):
    """A working store, so `spend` can actually refuse a replay."""
    class _FakeRedis:
        def __init__(self):
            self.keys = {}

        def set(self, key, value, nx=False, ex=None):
            if nx and key in self.keys:
                return None
            self.keys[key] = value
            return True

    from app.core import limits

    store = _FakeRedis()
    monkeypatch.setattr(limits, "_redis", lambda: store)
    return store


def test_a_nonce_can_be_spent_once(spendable):
    assert nonce.spend("abc123", ttl_seconds=60) is True
    assert nonce.spend("abc123", ttl_seconds=60) is False


def test_different_nonces_do_not_collide(spendable):
    assert nonce.spend("first", ttl_seconds=60) is True
    assert nonce.spend("second", ttl_seconds=60) is True


def test_an_unreachable_store_lets_the_token_through(monkeypatch, caplog):
    """Deliberate, and strictly no worse than what it replaced.

    Failing closed would stop every third-party sign-in whenever Redis
    blinks, to close a window that already requires an attacker to hold a
    sixty-second credential. Before this existed, nothing was burned at all.
    """
    from app.core import limits

    monkeypatch.setattr(limits, "_redis", lambda: (_ for _ in ()).throw(OSError("down")))

    assert nonce.spend("abc123", ttl_seconds=60) is True
    assert any("allowing it" in record.message for record in caplog.records)


def test_the_handoff_token_carries_a_claim_to_burn():
    """Without a `jti` there is nothing to remember, so nothing to refuse."""
    import inspect

    from app.api.routes import oauth

    source = inspect.getsource(oauth.callback)
    assert '"jti"' in source


def test_the_exchange_burns_the_token(raw_client, spendable, db):
    """A second exchange of the same cookie is refused.

    The cookie was always cleared; the *token* was not spent, so a copy taken
    from anywhere the browser had been stayed valid for the full minute.
    """
    from datetime import timedelta

    from app.repositories import users as users_repo

    user = users_repo.create_web_user(db, email="oauth@example.com",
                                      password_hash="x")
    db.commit()

    handoff = security.sign_payload(
        {"sub": str(user.id), "ver": user.token_version, "jti": "replay-me"},
        kind=security.HANDOFF, lifetime=timedelta(seconds=60),
    )

    first = raw_client.post("/api/auth/oauth/exchange",
                            cookies={"finmentor_handoff": handoff})
    assert first.status_code == 200, first.text

    second = raw_client.post("/api/auth/oauth/exchange",
                             cookies={"finmentor_handoff": handoff})

    assert second.status_code == 401
    assert "already been used" in second.json()["error"]["message"]


# --- S6 and S7: what the repository ships --------------------------------

def _repo_root():
    import pathlib

    return pathlib.Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("service", ["5432", "6379"])
def test_the_demo_stack_does_not_publish_its_datastores_to_the_world(service):
    """Docker publishes a bare `"5432:5432"` on 0.0.0.0.

    On anything that is not a laptop that put a Postgres with the password
    `finmentor`, and a Redis with no password at all, on the network.
    """
    # Directives only. The comment above each mapping quotes the old form in
    # order to explain why it changed, and a check that read the comments
    # would fail on its own explanation.
    directives = "\n".join(
        line for line in (_repo_root() / "docker-compose.yml")
        .read_text(encoding="utf-8").splitlines()
        if not line.lstrip().startswith("#")
    )

    assert f'"{service}:{service}"' not in directives, \
        f"port {service} is published on every interface"
    assert f'"127.0.0.1:{service}:{service}"' in directives


@pytest.mark.parametrize("pattern", ["*.log", ".coverage", "video/"])
def test_runtime_artefacts_are_ignored(pattern):
    """`bot.log` alone was listed, which is how `bot.err.log` got committed."""
    ignored = (_repo_root() / ".gitignore").read_text(encoding="utf-8")

    assert pattern in ignored


def test_no_runtime_log_is_tracked():
    """The check that would have caught the 220 KB of stack traces."""
    import subprocess

    tracked = subprocess.run(
        ["git", "ls-files"], cwd=_repo_root(), capture_output=True, text=True,
    ).stdout.splitlines()

    offenders = [
        path for path in tracked
        if path.endswith(".log") or path.endswith(".coverage")
        or path.lower().endswith((".mp4", ".mov"))
    ]
    assert offenders == [], f"tracked runtime artefacts: {offenders}"
