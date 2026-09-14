"""Web authentication, and the guard on everything else.

These use `raw_client` — no dependency overrides — so what is exercised is the
API exactly as a browser meets it. The rest of the suite overrides the guard
because it is about business logic; this file is where the guard itself is the
subject.
"""
import time

import pytest

from app.api.deps import require_user
from app.api.routes import ALL_ROUTERS
from app.core import security
from app.core.config import settings
from app.schemas.auth import MIN_PASSWORD_LENGTH
from tests.conftest import error_message

EMAIL = "sam@example.com"
PASSWORD = "a-long-enough-password"


def signup(client, email=EMAIL, password=PASSWORD):
    return client.post("/api/auth/signup", json={"email": email, "password": password})


def login(client, email=EMAIL, password=PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def tokens(raw_client) -> dict:
    return signup(raw_client).json()


# --- signup --------------------------------------------------------------

def test_signup_creates_a_user_and_returns_a_token_pair(raw_client, db):
    from app.repositories import users as users_repo

    response = signup(raw_client)

    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == settings.access_token_ttl_minutes * 60
    assert security.decode_token(body["access_token"]) > 0

    user = users_repo.get_by_email(db, EMAIL)
    assert user is not None
    assert user.telegram_id is None          # a web user has no telegram id


def test_the_password_is_never_stored_in_the_clear(raw_client, db):
    from app.repositories import users as users_repo

    signup(raw_client)
    stored = users_repo.get_by_email(db, EMAIL).password_hash

    assert PASSWORD not in stored
    assert stored.startswith("$argon2")


def test_the_password_never_appears_in_a_response(raw_client):
    body = signup(raw_client).text
    assert PASSWORD not in body


def test_an_email_is_normalised_so_case_does_not_create_two_accounts(raw_client):
    assert signup(raw_client, email="Sam@Example.COM").status_code == 201
    assert signup(raw_client, email="sam@example.com").status_code == 409


def test_a_duplicate_email_is_409(raw_client):
    signup(raw_client)
    assert signup(raw_client).status_code == 409


@pytest.mark.parametrize("password", ["short", "x" * (MIN_PASSWORD_LENGTH - 1)])
def test_a_short_password_is_422(raw_client, password):
    assert signup(raw_client, password=password).status_code == 422


def test_a_malformed_email_is_422(raw_client):
    assert signup(raw_client, email="not-an-email").status_code == 422


# --- login ---------------------------------------------------------------

def test_login_returns_a_fresh_pair(raw_client):
    signup(raw_client)
    response = login(raw_client)

    assert response.status_code == 200
    assert security.decode_token(response.json()["access_token"]) > 0


def test_a_wrong_password_is_401(raw_client):
    signup(raw_client)
    assert login(raw_client, password="the-wrong-password").status_code == 401


def test_an_unknown_email_is_401(raw_client):
    assert login(raw_client, email="nobody@example.com").status_code == 401


def test_the_two_failures_are_indistinguishable(raw_client):
    """Different messages would tell an attacker which emails are registered."""
    signup(raw_client)
    wrong_password = login(raw_client, password="the-wrong-password")
    unknown_email = login(raw_client, email="nobody@example.com")

    # Everything except the request id, which is deliberately unique per
    # request and carries nothing about which account was tried.
    def without_request_id(response):
        body = response.json()["error"]
        return {k: v for k, v in body.items() if k != "request_id"}

    assert without_request_id(wrong_password) == without_request_id(unknown_email)
    assert wrong_password.status_code == unknown_email.status_code


def test_a_telegram_user_cannot_be_logged_into(raw_client, db):
    """No password hash means no password verifies — not a crash, a 401."""
    from app.repositories import users as users_repo

    users_repo.create(db, telegram_id=771_001)
    db.commit()

    assert login(raw_client, email="whatever@example.com").status_code == 401


# --- refresh -------------------------------------------------------------

def test_refresh_issues_a_new_pair(raw_client, tokens):
    response = raw_client.post("/api/auth/refresh",
                               json={"refresh_token": tokens["refresh_token"]})

    assert response.status_code == 200
    assert security.decode_token(response.json()["access_token"]) > 0


def test_an_access_token_is_not_accepted_as_a_refresh_token(raw_client, tokens):
    """Without the `typ` check every session would quietly last 14 days."""
    response = raw_client.post("/api/auth/refresh",
                               json={"refresh_token": tokens["access_token"]})

    assert response.status_code == 401


def test_a_refresh_token_is_not_accepted_as_an_access_token(raw_client, tokens):
    response = raw_client.get("/api/auth/me", headers=auth(tokens["refresh_token"]))

    assert response.status_code == 401


def test_a_garbage_refresh_token_is_401(raw_client):
    assert raw_client.post("/api/auth/refresh",
                           json={"refresh_token": "not.a.token"}).status_code == 401


def test_a_token_for_a_deleted_user_is_401(raw_client, db, tokens):
    from app.repositories import users as users_repo

    user_id = security.decode_token(tokens["access_token"])
    users_repo.delete(db, users_repo.get(db, user_id))
    db.commit()

    assert raw_client.get("/api/auth/me", headers=auth(tokens["access_token"])).status_code == 401


# --- me ------------------------------------------------------------------

def test_me_reports_the_signed_in_user(raw_client, tokens):
    body = raw_client.get("/api/auth/me", headers=auth(tokens["access_token"])).json()

    assert body["email"] == EMAIL
    assert body["telegram_id"] is None
    assert body["onboarded"] is False


def test_logout_is_a_204_and_needs_nothing(raw_client):
    assert raw_client.post("/api/auth/logout").status_code == 204


# --- the tokens themselves ----------------------------------------------

def test_an_expired_access_token_is_401(raw_client, tokens, monkeypatch):
    monkeypatch.setattr(settings, "access_token_ttl_minutes", -1)
    expired = security.create_access_token(security.decode_token(tokens["access_token"]))

    assert raw_client.get("/api/auth/me", headers=auth(expired)).status_code == 401


def test_a_token_signed_with_another_secret_is_401(raw_client, tokens, monkeypatch):
    user_id = security.decode_token(tokens["access_token"])
    monkeypatch.setattr(settings, "jwt_secret", "a-completely-different-secret-value")
    forged = security.create_access_token(user_id)
    monkeypatch.undo()

    assert raw_client.get("/api/auth/me", headers=auth(forged)).status_code == 401


@pytest.mark.parametrize(
    "header", [None, "", "Bearer", "Bearer ", "Basic abc", "abc", "bearer"]
)
def test_a_malformed_authorization_header_is_401(raw_client, header):
    headers = {} if header is None else {"Authorization": header}
    assert raw_client.get("/api/auth/me", headers=headers).status_code == 401


def test_the_challenge_says_bearer(raw_client):
    """So a client can tell "log in" from "not allowed"."""
    response = raw_client.get("/api/auth/me")

    assert response.headers.get("WWW-Authenticate") == "Bearer"


def test_an_access_token_is_short_lived_and_a_refresh_token_is_not(tokens):
    import jwt

    access = jwt.decode(tokens["access_token"], settings.jwt_secret, algorithms=["HS256"])
    refresh = jwt.decode(tokens["refresh_token"], settings.jwt_secret, algorithms=["HS256"])

    assert access["typ"] == "access" and refresh["typ"] == "refresh"
    assert refresh["exp"] - access["exp"] > 60 * 60      # days apart, not minutes
    assert access["exp"] - time.time() <= settings.access_token_ttl_minutes * 60 + 5


# --- every other route is guarded ---------------------------------------

GUARDED = [
    ("GET", "/api/users/1"),
    ("POST", "/api/users"),
    ("GET", "/api/financial-profile/1"),
    ("PUT", "/api/financial-profile/1"),
    ("GET", "/api/health/1"),
    ("GET", "/api/health/1/dna"),
    ("GET", "/api/goals/1"),
    ("POST", "/api/goals"),
    ("PUT", "/api/goals/1"),
    ("POST", "/api/simulations"),
    ("GET", "/api/simulations/1"),
    ("GET", "/api/market/assets"),
    ("GET", "/api/market/assets/BTC"),
    ("GET", "/api/market/watchlist/1"),
    ("POST", "/api/market/watchlist/1"),
    ("DELETE", "/api/market/watchlist/1/BTC"),
    ("GET", "/api/learn"),
    ("GET", "/api/learn/budgeting"),
    ("POST", "/api/learn/budgeting/quiz"),
    ("GET", "/api/me/summary"),
    ("POST", "/api/ai/ask"),
    ("GET", "/api/ai/transcript/1"),
]


@pytest.mark.parametrize("method,path", GUARDED, ids=lambda v: str(v))
def test_no_route_answers_without_a_token(raw_client, method, path):
    """The whole API, one case each. A route added to a guarded router without
    a token requirement shows up here as a passing request."""
    response = raw_client.request(method, path, json={})

    assert response.status_code == 401, f"{method} {path} answered {response.status_code}"


OPEN = [("POST", "/api/auth/signup"), ("POST", "/api/auth/login"),
        ("POST", "/api/auth/refresh"), ("POST", "/api/auth/logout"),
        ("GET", "/healthz"), ("GET", "/api/market/public/BTC")]


#: Every path that answers without a token, as a path template. The list above
#: proves these *stay* open; this one is the inventory the next test checks the
#: application against, so adding a public route means adding a line here
#: rather than discovering later that one slipped through.
PUBLIC_PATHS = {
    "/api/auth/signup",
    "/api/auth/login",
    "/api/auth/refresh",
    "/api/auth/logout",
    # The live-price WebSocket and the series that seeds its sparkline. A
    # current price is not personal data; both are capped, origin-checked or
    # cache-only, and neither can reach another user's rows.
    "/api/market/live",
    "/api/market/public/{symbol}",
}


def _is_guarded(router, route) -> bool:
    """Whether `require_user` runs for this route, from either direction.

    Most routers carry it once, at the router, which is what makes a route
    added later guarded by default. `/api/auth/me` is the exception: it sits
    on the open auth router and declares the dependency itself.
    """
    if any(getattr(d, "dependency", None) is require_user for d in router.dependencies):
        return True
    dependant = getattr(route, "dependant", None)
    return dependant is not None and any(
        d.call is require_user for d in dependant.dependencies
    )


def test_every_route_is_guarded_or_listed_as_public():
    """The guard, checked against the application rather than against a list.

    `GUARDED` above is hand-maintained, so a new unguarded route would simply
    not appear in it and nothing would fail. This walks the real router tree
    instead: a route that is neither guarded nor named in `PUBLIC_PATHS` is a
    failure at the moment it is written.
    """
    unguarded = [
        route.path
        for router in ALL_ROUTERS
        for route in router.routes
        if not _is_guarded(router, route) and route.path not in PUBLIC_PATHS
    ]

    assert unguarded == [], f"unguarded routes not declared public: {unguarded}"


@pytest.mark.parametrize("method,path", OPEN, ids=lambda v: str(v))
def test_the_open_routes_stay_open(raw_client, method, path):
    response = raw_client.request(method, path, json={})

    assert response.status_code != 401


# --- a user may only reach their own data -------------------------------

@pytest.fixture
def two_users(raw_client):
    mine = signup(raw_client, email="mine@example.com").json()
    theirs = signup(raw_client, email="theirs@example.com").json()
    return (security.decode_token(mine["access_token"]), mine["access_token"],
            security.decode_token(theirs["access_token"]))


CROSS_USER = [
    ("GET", "/api/users/{id}"),
    ("GET", "/api/financial-profile/{id}"),
    ("GET", "/api/health/{id}"),
    ("GET", "/api/health/{id}/dna"),
    ("GET", "/api/goals/{id}"),
    ("GET", "/api/simulations/{id}"),
    ("GET", "/api/market/watchlist/{id}"),
    ("GET", "/api/ai/transcript/{id}"),
]


@pytest.mark.parametrize("method,template", CROSS_USER, ids=lambda v: str(v))
def test_reading_another_users_data_is_403(raw_client, two_users, method, template):
    _, my_token, their_id = two_users

    response = raw_client.request(method, template.format(id=their_id),
                                  headers=auth(my_token), json={})

    assert response.status_code == 403, \
        f"{method} {template} answered {response.status_code}"


def test_writing_a_goal_for_another_user_is_403(raw_client, two_users):
    _, my_token, their_id = two_users

    response = raw_client.post("/api/goals", headers=auth(my_token), json={
        "user_id": their_id, "name": "Theirs", "target_amount": 1_000_000,
    })

    assert response.status_code == 403


def test_asking_the_ai_as_another_user_is_403(raw_client, two_users):
    _, my_token, their_id = two_users

    response = raw_client.post("/api/ai/ask", headers=auth(my_token),
                               json={"user_id": their_id, "question": "how am I doing?"})

    assert response.status_code == 403


def test_running_a_simulation_as_another_user_is_403(raw_client, two_users):
    _, my_token, their_id = two_users

    response = raw_client.post("/api/simulations", headers=auth(my_token), json={
        "user_id": their_id, "kind": "decision", "params": {"price": 1_000_000},
    })

    assert response.status_code == 403


def test_my_own_data_is_reachable(raw_client, two_users):
    my_id, my_token, _ = two_users

    assert raw_client.get(f"/api/users/{my_id}", headers=auth(my_token)).status_code == 200


def test_a_403_is_not_a_404(raw_client, two_users):
    """The caller is authenticated and the resource exists. Saying "not found"
    would be a lie they cannot act on."""
    _, my_token, their_id = two_users
    response = raw_client.get(f"/api/users/{their_id}", headers=auth(my_token))

    assert response.status_code == 403
    assert "your own" in error_message(response)
