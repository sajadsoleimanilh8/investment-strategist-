"""Forgotten passwords, end to end.

The transport is the console mailer, which is the default and what the test
suite runs on: the message is logged rather than sent, so these tests read the
link out of the captured log exactly as a developer or an offline demo would.
That is not a simulation of the flow — it is the flow, with the last hop
replaced by the transport the configuration selected.

What the assertions are mostly about is what the API refuses to tell anyone:
whether an address is registered, and which of the three ways a bad link can
be bad it is.
"""
from __future__ import annotations

import logging
import re

import pytest

from app.core import security
from app.models.auth import PasswordReset
from app.repositories import users as users_repo
from tests.api.test_auth import EMAIL, PASSWORD, auth, login, signup
from tests.conftest import error_message

NEW_PASSWORD = "an-even-longer-password"


def forgot(client, email=EMAIL):
    return client.post("/api/auth/forgot-password", json={"email": email})


def reset(client, token, password=NEW_PASSWORD):
    return client.post("/api/auth/reset-password",
                       json={"token": token, "password": password})


def link_token(caplog) -> str:
    """The raw token out of the logged email.

    Reading the log is the point: with the console transport this is where the
    link goes, and a test that fished the token out of the database instead
    would pass even if the email never contained one.
    """
    match = re.search(r"reset-password\?token=([\w\-]+)", caplog.text)
    assert match, f"no reset link in the logged email:\n{caplog.text}"
    return match.group(1)


@pytest.fixture
def requested(raw_client, caplog):
    """A signed-up user who has asked for a link, and the link they got."""
    signup(raw_client)
    with caplog.at_level(logging.INFO, logger="finmentor.mail"):
        assert forgot(raw_client).status_code == 202
        return link_token(caplog)


# --- what the request tells the world ------------------------------------

def test_an_unknown_address_answers_exactly_like_a_known_one(raw_client, caplog):
    """The two responses have to be indistinguishable, or this endpoint is a
    way to find out who has an account here."""
    signup(raw_client)

    known = forgot(raw_client, EMAIL)
    unknown = forgot(raw_client, "nobody@example.com")

    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()


def test_no_email_is_sent_for_an_address_with_no_account(raw_client, caplog):
    with caplog.at_level(logging.INFO, logger="finmentor.mail"):
        forgot(raw_client, "nobody@example.com")

    assert "reset-password?token=" not in caplog.text


def test_the_email_carries_a_link_the_web_app_can_open(raw_client, caplog):
    """Not the API endpoint: the link has to open a *page*, and in a split
    deployment the two are different origins."""
    signup(raw_client)
    with caplog.at_level(logging.INFO, logger="finmentor.mail"):
        forgot(raw_client)

    assert "/reset-password?token=" in caplog.text


def test_the_token_is_never_stored_in_the_clear(raw_client, db, requested):
    """A reset row is a bearer credential. A database leak must not also be a
    leak of working links."""
    stored = db.query(PasswordReset).one()

    assert stored.token_hash != requested
    assert stored.token_hash == security.hash_reset_token(requested)


# --- spending the link ----------------------------------------------------

def test_a_valid_link_sets_the_password_and_signs_the_user_in(raw_client, requested):
    response = reset(raw_client, requested)

    assert response.status_code == 200
    assert response.json()["access_token"]
    assert login(raw_client, password=NEW_PASSWORD).status_code == 200
    assert login(raw_client, password=PASSWORD).status_code == 401


def test_the_pair_it_returns_actually_works(raw_client, requested):
    """The bump this reset performs must not refuse the session it just
    created: the pair is minted after it, under the new version."""
    pair = reset(raw_client, requested).json()

    assert raw_client.get("/api/auth/me", headers=auth(pair["access_token"])).status_code == 200


def test_a_link_works_once(raw_client, requested):
    assert reset(raw_client, requested).status_code == 200

    again = reset(raw_client, requested, "a-third-password-entirely")

    assert again.status_code == 400
    assert login(raw_client, password="a-third-password-entirely").status_code == 401


def test_asking_again_retires_the_first_link(raw_client, caplog):
    """Two working keys to one account sitting in one inbox is the situation
    this avoids, and the person who asks twice is the likeliest to be having
    their mail read."""
    signup(raw_client)
    with caplog.at_level(logging.INFO, logger="finmentor.mail"):
        forgot(raw_client)
        first = link_token(caplog)
        caplog.clear()
        forgot(raw_client)
        second = link_token(caplog)

    assert reset(raw_client, first).status_code == 400
    assert reset(raw_client, second).status_code == 200


def test_an_expired_link_is_refused(raw_client, db, requested, monkeypatch):
    stored = db.query(PasswordReset).one()
    # Reach into the row rather than the clock: the expiry is data, and moving
    # it is exactly what the passage of time would have done.
    from datetime import datetime, timedelta, timezone
    stored.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()

    assert reset(raw_client, requested).status_code == 400


def test_a_made_up_token_is_refused(raw_client):
    assert reset(raw_client, "not-a-real-token").status_code == 400


def test_every_refusal_reads_the_same(raw_client, requested):
    """Expired, spent and never-existed are one message. The difference is not
    something the holder of a bad link can act on, and each distinction is a
    thing worth learning by guessing."""
    reset(raw_client, requested)

    # The request id differs by design; the sentence is the part a caller can
    # learn anything from, and it must not differ.
    spent = error_message(reset(raw_client, requested))
    invented = error_message(reset(raw_client, "not-a-real-token"))

    assert spent == invented


def test_a_short_password_is_rejected_by_the_schema(raw_client, requested):
    assert reset(raw_client, requested, "short").status_code == 422


# --- what the reset does to sessions the old password started ------------

def test_it_ends_the_sessions_the_old_password_could_have_started(raw_client, requested):
    """The reason to reset is that somebody else may have the old password.
    A session it started outliving the reset would defeat the whole exercise:
    these tokens are signed, unexpired and stateless, so nothing but the
    version bump stops them."""
    before = signup_then_login_token(raw_client)

    reset(raw_client, requested)

    assert raw_client.get("/api/auth/me", headers=auth(before)).status_code == 401


def signup_then_login_token(client) -> str:
    """An access token for the account, taken the ordinary way."""
    return login(client).json()["access_token"]


def test_an_account_that_never_reset_keeps_its_sessions(raw_client):
    """Version 0 is where every account starts, and a token minted at 0 has
    to keep working for an account that has never reset."""
    token = signup(raw_client).json()["access_token"]

    assert raw_client.get("/api/auth/me", headers=auth(token)).status_code == 200


def test_the_refresh_token_from_before_the_reset_stops_working(raw_client, requested):
    old_refresh = login(raw_client).json()["refresh_token"]

    reset(raw_client, requested)
    refreshed = raw_client.post("/api/auth/refresh", json={"refresh_token": old_refresh})

    # It refreshes into an access token the guard then refuses, which is the
    # same outcome by a different door: nothing minted before the cutoff works.
    if refreshed.status_code == 200:
        token = refreshed.json()["access_token"]
        assert raw_client.get("/api/auth/me", headers=auth(token)).status_code == 401


# --- a transport that is down --------------------------------------------

def test_a_mail_failure_does_not_change_the_answer(raw_client, monkeypatch):
    """A 500 on one address and a 202 on another is an account-existence
    oracle with extra steps."""
    signup(raw_client)

    def explode(message):
        raise RuntimeError("smtp is down")

    monkeypatch.setattr("app.core.mailer.build_mailer",
                        lambda: type("Broken", (), {"send": staticmethod(explode)})())

    assert forgot(raw_client).status_code == 202


def test_a_user_with_no_password_can_still_be_sent_one(raw_client, db, caplog):
    """A Telegram-only row has `password_hash = None`. Reset is how that
    account gains a web login, so it is not an error path."""
    signup(raw_client)
    user = users_repo.get_by_email(db, EMAIL)
    user.password_hash = None
    db.commit()

    with caplog.at_level(logging.INFO, logger="finmentor.mail"):
        assert forgot(raw_client).status_code == 202
        token = link_token(caplog)

    assert reset(raw_client, token).status_code == 200
