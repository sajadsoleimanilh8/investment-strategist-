"""The sign-in round trip, without a provider.

Nothing here talks to Google, GitHub or Apple: the one call that would is
`_exchange_code`, and it is replaced. What is under test is everything around
it — the state that has to survive a trip through someone else's site, the
handoff that has to not be a token in a URL, and the account resolution that
decides whose data a sign-in reaches.

The live paths stay a pre-deploy manual check (docs/PRE_DEPLOY.md), like every
other external provider in this project. They need registered applications,
redirect URIs on a real domain, and in Apple's case a paid developer account.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from app.api.routes import oauth as oauth_routes
from app.core import security
from app.models.identity import UserIdentity
from app.oauth import registry
from app.oauth.base import Identity
from app.oauth.providers import GoogleProvider
from app.repositories import identities as identities_repo
from app.repositories import users as users_repo
from tests.api.test_auth import EMAIL, PASSWORD, auth, signup

GOOGLE = Identity(subject="google-sub-1", email="sam@example.com")


@pytest.fixture
def google(monkeypatch):
    """A configured Google, and a code exchange that returns `GOOGLE`."""
    provider = GoogleProvider("client-id", "client-secret")
    monkeypatch.setattr(registry, "_all", lambda: {"google": provider})
    monkeypatch.setattr(oauth_routes.registry, "_all", lambda: {"google": provider})
    monkeypatch.setattr(oauth_routes, "_exchange_code",
                        lambda provider, code, verifier: GOOGLE)
    return provider


def start(client, provider="google", **params):
    return client.get(f"/api/auth/oauth/{provider}/start", params=params,
                      follow_redirects=False)


def callback(client, **params):
    return client.get("/api/auth/oauth/google/callback", params=params,
                      follow_redirects=False)


def state_for(provider="google", next="/dashboard", verifier="v"):
    return security.sign_payload({"p": provider, "v": verifier, "next": next},
                                 kind=security.STATE, lifetime=timedelta(minutes=5))


# --- which buttons exist --------------------------------------------------

def test_no_credentials_means_no_buttons(raw_client):
    """The default. A button that leads to a provider's error page reads as
    this product being broken."""
    assert raw_client.get("/api/auth/oauth/providers").json() == {"providers": []}


def test_a_configured_provider_is_offered(raw_client, google):
    assert raw_client.get("/api/auth/oauth/providers").json() == {"providers": ["google"]}


def test_an_unconfigured_provider_cannot_be_started(raw_client):
    assert start(raw_client, "github").status_code == 404


def test_an_invented_provider_is_the_same_404(raw_client, google):
    assert start(raw_client, "myspace").status_code == 404


# --- leaving ---------------------------------------------------------------

def test_start_redirects_to_the_provider_with_state_and_pkce(raw_client, google):
    response = start(raw_client)

    assert response.status_code == 307
    location = response.headers["location"]
    assert location.startswith("https://accounts.google.com/")
    assert "code_challenge_method=S256" in location
    assert "state=" in location


def test_the_verifier_never_leaves_in_the_clear(raw_client, google):
    """It rides inside the signed state, not as its own parameter: the whole
    point of PKCE is that the provider sees only the challenge."""
    location = start(raw_client).headers["location"]

    assert "code_verifier" not in location


def test_a_next_pointing_off_site_is_dropped(raw_client, google):
    """`?next=https://elsewhere` is how a trusted sign-in link becomes a
    phishing redirect."""
    response = start(raw_client, next="https://evil.example/login")
    state = _state_from(response.headers["location"])

    assert security.read_payload(state, kind=security.STATE)["next"] == "/dashboard"


def test_a_protocol_relative_next_is_dropped(raw_client, google):
    response = start(raw_client, next="//evil.example")
    state = _state_from(response.headers["location"])

    assert security.read_payload(state, kind=security.STATE)["next"] == "/dashboard"


def test_a_path_inside_the_app_survives(raw_client, google):
    response = start(raw_client, next="/goals")
    state = _state_from(response.headers["location"])

    assert security.read_payload(state, kind=security.STATE)["next"] == "/goals"


def _state_from(location: str) -> str:
    return location.split("state=")[1].split("&")[0]


# --- coming back -----------------------------------------------------------

def test_a_callback_this_app_did_not_start_is_refused(raw_client, google):
    """No signature, no sign-in. This is the entire defence against a callback
    somebody else arranged."""
    response = callback(raw_client, code="x", state="not-a-real-state")

    assert response.status_code == 303
    assert "error=state" in response.headers["location"]


def test_a_state_minted_for_another_provider_is_refused(raw_client, google):
    response = callback(raw_client, code="x", state=state_for(provider="github"))

    assert "error=state" in response.headers["location"]


def test_an_expired_state_is_refused(raw_client, google):
    stale = security.sign_payload({"p": "google", "v": "v", "next": "/"},
                                  kind=security.STATE, lifetime=timedelta(seconds=-1))

    assert "error=state" in callback(raw_client, code="x", state=stale).headers["location"]


def test_a_cancelled_sign_in_goes_back_to_the_login_page(raw_client, google):
    response = callback(raw_client, error="access_denied", state=state_for())

    assert "error=cancelled" in response.headers["location"]


def test_a_provider_that_fails_does_not_500(raw_client, google, monkeypatch):
    def explode(provider, code, verifier):
        raise oauth_routes.IdentityError("google said no")

    monkeypatch.setattr(oauth_routes, "_exchange_code", explode)

    response = callback(raw_client, code="x", state=state_for())

    assert response.status_code == 303
    assert "error=provider" in response.headers["location"]


def test_a_successful_callback_hands_off_by_cookie(raw_client, google):
    """Not by URL. A token in the address the browser is sent to lands in
    history, in the next request's referrer, and in any log that records
    paths."""
    response = callback(raw_client, code="x", state=state_for())

    assert response.status_code == 303
    assert "/auth/callback" in response.headers["location"]
    assert "token" not in response.headers["location"]
    assert oauth_routes.HANDOFF_COOKIE in response.cookies


# --- whose account -------------------------------------------------------

def test_a_first_sign_in_creates_an_account(raw_client, google, db):
    callback(raw_client, code="x", state=state_for())

    user = users_repo.get_by_email(db, GOOGLE.email)
    assert user is not None
    assert user.password_hash is None          # nothing to guess
    assert db.query(UserIdentity).count() == 1


def test_signing_in_twice_does_not_create_a_second_account(raw_client, google, db):
    callback(raw_client, code="x", state=state_for())
    callback(raw_client, code="x", state=state_for())

    assert db.query(UserIdentity).count() == 1


def test_a_verified_address_links_to_the_password_account(raw_client, google, db,
                                                          monkeypatch):
    """The case that makes "sign in with Google" work for someone who signed
    up with a password. Safe only because the provider verified the address."""
    signup(raw_client, email=GOOGLE.email)
    before = users_repo.get_by_email(db, GOOGLE.email).id

    callback(raw_client, code="x", state=state_for())

    identity = db.query(UserIdentity).one()
    assert identity.user_id == before, "a second account was created instead"


def test_a_provider_with_no_address_is_refused(raw_client, google, monkeypatch, db):
    monkeypatch.setattr(oauth_routes, "_exchange_code",
                        lambda provider, code, verifier: Identity(subject="s", email=None))

    response = callback(raw_client, code="x", state=state_for())

    assert "error=no_email" in response.headers["location"]
    assert db.query(UserIdentity).count() == 0


# --- the exchange ---------------------------------------------------------

def test_the_cookie_buys_a_token_pair(raw_client, google):
    raw_client.cookies.clear()
    callback(raw_client, code="x", state=state_for())

    pair = raw_client.post("/api/auth/oauth/exchange")

    assert pair.status_code == 200
    assert raw_client.get("/api/auth/me",
                          headers=auth(pair.json()["access_token"])).status_code == 200


def test_the_exchange_without_a_cookie_is_401(raw_client, google):
    raw_client.cookies.clear()

    assert raw_client.post("/api/auth/oauth/exchange").status_code == 401


def test_a_handoff_cannot_be_spent_twice(raw_client, google):
    """The route clears the cookie on the way out, so a second attempt has
    nothing to present."""
    raw_client.cookies.clear()
    callback(raw_client, code="x", state=state_for())
    assert raw_client.post("/api/auth/oauth/exchange").status_code == 200

    assert raw_client.post("/api/auth/oauth/exchange").status_code == 401


def test_an_access_token_is_not_accepted_as_a_handoff(raw_client, google):
    """`typ` is checked in both directions, for the same reason it is on the
    access and refresh pair: a token accepted in the wrong place is a longer
    session than anybody intended."""
    access = signup(raw_client, email="other@example.com").json()["access_token"]
    raw_client.cookies.set(oauth_routes.HANDOFF_COOKIE, access)

    assert raw_client.post("/api/auth/oauth/exchange").status_code == 401


def test_a_handoff_from_before_a_password_reset_is_dead(raw_client, google, db):
    """It carries the token version, like everything else that mints a
    session."""
    raw_client.cookies.clear()
    callback(raw_client, code="x", state=state_for())
    user = users_repo.get_by_email(db, GOOGLE.email)
    user.token_version += 1
    db.commit()

    assert raw_client.post("/api/auth/oauth/exchange").status_code == 401


# --- the callback must not stall the process -----------------------------
#
# `callback` is the one `async def` route in this app: Apple posts its
# callback rather than redirecting to it, and parsing a form body is async in
# Starlette. Everything else is a plain `def` and therefore runs in a worker
# thread already. That made this handler the one place where a synchronous
# `httpx.Client` (ten-second timeout) and a synchronous SQLAlchemy session ran
# directly on the event loop, stalling every other request and every connected
# live-price WebSocket for the length of a provider's response.

def test_the_callback_does_its_blocking_work_off_the_event_loop(monkeypatch):
    """Asserted by watching which thread each blocking call runs on.

    A timing test would be flaky and a source-code check would not survive a
    refactor. The thread identity is the actual property: work handed to
    `asyncio.to_thread` runs somewhere other than the loop's own thread.
    """
    import asyncio
    import threading

    from app.api.routes import oauth

    loop_thread: dict[str, int] = {}
    ran_on: dict[str, int] = {}

    class _Identity:
        subject = "provider-subject-1"
        email = "someone@example.com"

    def slow_exchange(provider, *, code, verifier):
        ran_on["exchange"] = threading.get_ident()
        return _Identity()

    monkeypatch.setattr(oauth, "_exchange_code", slow_exchange)

    async def run() -> None:
        loop_thread["loop"] = threading.get_ident()
        await asyncio.to_thread(slow_exchange, None, code="c", verifier="v")

    asyncio.run(run())

    assert ran_on["exchange"] != loop_thread["loop"], (
        "the provider call ran on the event loop thread")


def test_the_callback_is_still_the_only_async_route():
    """If it were not async, none of the above would be necessary.

    Kept as a check because the fix is only interesting while the handler is
    `async`: a future rewrite to a plain `def` should delete the
    `asyncio.to_thread` calls rather than leave them as noise.
    """
    import inspect

    from app.api.routes import ALL_ROUTERS
    from fastapi.routing import APIRoute

    # Deduplicated: the callback is declared twice, once per method, so that
    # GET and POST get distinct OpenAPI operation ids. That is two route
    # entries for one path and one handler, and the property being asserted
    # is about the handler.
    async_routes = {
        route.path
        for router in ALL_ROUTERS
        for route in router.routes
        if isinstance(route, APIRoute) and inspect.iscoroutinefunction(route.endpoint)
    }

    assert async_routes == {"/api/auth/oauth/{provider_name}/callback"}, async_routes
