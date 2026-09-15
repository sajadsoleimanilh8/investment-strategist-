"""What each provider does with what it is told.

No network: `verify_id_token` is the one piece that must talk to a provider
(to fetch signing keys) and it is replaced here, because what these tests are
about is the policy applied to the claims, not PyJWT's ability to check a
signature.

The policy is mostly one rule: an address the provider has not verified is a
claim, not an identity. `identities.resolve` links a provider sign-in to an
existing account by address, so an unverified one would let anybody with a
Google account take over a FinMentor account by typing someone else's address
into their profile.
"""
from __future__ import annotations

import pytest

from app.core.config import Settings
from app.oauth import providers as provider_module
from app.oauth.base import IdentityError
from app.oauth.providers import AppleProvider, GitHubProvider, GoogleProvider


@pytest.fixture
def claims(monkeypatch):
    """Make `verify_id_token` return whatever a test puts in `claims.value`."""
    holder = type("Holder", (), {"value": {}})()
    monkeypatch.setattr(provider_module, "verify_id_token",
                        lambda *a, **kw: holder.value)
    return holder


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class FakeClient:
    """Enough of httpx.Client for GitHub's two calls."""

    def __init__(self, routes: dict):
        self.routes = routes
        self.seen: list[str] = []

    def get(self, url, headers=None):
        self.seen.append(url)
        return FakeResponse(self.routes[url])


# --- Google ---------------------------------------------------------------

def test_google_accepts_a_verified_address(claims):
    claims.value = {"sub": "1234", "email": "sam@example.com", "email_verified": True}

    identity = GoogleProvider("id", "secret").identity({"id_token": "x"}, None)

    assert identity.subject == "1234"
    assert identity.email == "sam@example.com"


def test_google_refuses_an_unverified_address(claims):
    claims.value = {"sub": "1234", "email": "victim@example.com", "email_verified": False}

    with pytest.raises(IdentityError):
        GoogleProvider("id", "secret").identity({"id_token": "x"}, None)


def test_the_subject_is_the_id_not_the_address(claims):
    """People change the address on a Google account. The account is the same
    account, and the subject is what says so."""
    claims.value = {"sub": "1234", "email": "new@example.com", "email_verified": True}

    identity = GoogleProvider("id", "secret").identity({"id_token": "x"}, None)

    assert identity.subject == "1234"


# --- Apple ----------------------------------------------------------------

def test_apple_accepts_a_string_flag(claims):
    """Apple sends `email_verified` as "true" on some paths and True on
    others. Both mean verified, and a strict `is True` refuses half of them."""
    claims.value = {"sub": "0001", "email": "sam@privaterelay.appleid.com",
                    "email_verified": "true"}

    identity = AppleProvider("id", "").identity({"id_token": "x"}, None)

    assert identity.email == "sam@privaterelay.appleid.com"


def test_apple_accepts_a_missing_flag_for_a_relay_address(claims):
    """Omitted for a private relay address, which is verified by construction:
    Apple owns the domain and forwards the mail."""
    claims.value = {"sub": "0001", "email": "x@privaterelay.appleid.com"}

    assert AppleProvider("id", "").identity({"id_token": "x"}, None).email


def test_apple_refuses_a_flag_that_says_no(claims):
    claims.value = {"sub": "0001", "email": "victim@example.com",
                    "email_verified": "false"}

    with pytest.raises(IdentityError):
        AppleProvider("id", "").identity({"id_token": "x"}, None)


def test_apple_is_unconfigured_without_the_signing_key(monkeypatch):
    """A client id alone cannot mint the client secret, and a button that
    leads to Apple's error page is worse than no button."""
    monkeypatch.setattr(provider_module, "settings",
                        Settings(apple_client_id="com.example.app"))

    assert AppleProvider("com.example.app", "").configured is False


def test_apple_posts_its_callback_back():
    """`response_mode=form_post` is what asking for the email scope does, and
    the callback route has to accept POST because of it."""
    provider = AppleProvider("id", "")

    params = provider.authorize_params(redirect_uri="http://x/cb", state="s",
                                       code_challenge="c")

    assert provider.posts_back is True
    assert params["response_mode"] == "form_post"


# --- GitHub ---------------------------------------------------------------

def test_github_takes_the_primary_verified_address():
    """The profile's own `email` is whatever the person made public, which is
    often nothing and is never guaranteed verified."""
    client = FakeClient({
        "https://api.github.com/user": {"id": 99, "email": "public@example.com"},
        "https://api.github.com/user/emails": [
            {"email": "old@example.com", "primary": False, "verified": True},
            {"email": "real@example.com", "primary": True, "verified": True},
        ],
    })

    identity = GitHubProvider("id", "secret").identity({"access_token": "t"}, client)

    assert identity.subject == "99"
    assert identity.email == "real@example.com"


def test_github_ignores_an_unverified_primary():
    client = FakeClient({
        "https://api.github.com/user": {"id": 99},
        "https://api.github.com/user/emails": [
            {"email": "unverified@example.com", "primary": True, "verified": False},
        ],
    })

    identity = GitHubProvider("id", "secret").identity({"access_token": "t"}, client)

    assert identity.email is None


def test_github_without_a_token_is_an_identity_error():
    with pytest.raises(IdentityError):
        GitHubProvider("id", "secret").identity({}, FakeClient({}))


def test_github_sends_no_pkce_parameters():
    """Plain OAuth2. Sending them is harmless and claiming they protect the
    flow would not be true, so the flag says which it is."""
    params = GitHubProvider("id", "s").authorize_params(
        redirect_uri="http://x/cb", state="s", code_challenge="c")

    assert "code_challenge" not in params
