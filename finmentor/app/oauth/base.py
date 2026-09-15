"""What every third-party sign-in has in common.

Three providers, one shape: send the person to an authorize URL, get a code
back, trade the code for a token, and ask the provider who just signed in. The
differences are all in the last step, which is why that is the only method a
provider implements.

Deliberately hand-written rather than an OAuth library. The flow is a redirect
and two HTTP calls; what a library would add here is a dependency, a plugin
system and a set of defaults to audit, in exchange for code this file already
contains. The parts worth being careful about — `state`, PKCE, and never
trusting an id token without verifying it — are explicit below rather than
buried in a framework's configuration.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass

import httpx


@dataclass(frozen=True)
class Identity:
    """Who signed in, as far as the provider is concerned."""

    #: The provider's immutable id for the account. Never an email: people
    #: change those, and an account taken over by a new owner of a recycled
    #: address must not inherit the old owner's data.
    subject: str
    #: Verified addresses only. An unverified one is a claim, not a fact, and
    #: matching on it would let anyone with a provider account take over a
    #: FinMentor account by typing someone else's address into it.
    email: str | None


class OAuthProvider(abc.ABC):
    """One provider. Subclasses supply the endpoints and the identity call."""

    name: str = "base"
    authorize_url: str = ""
    token_url: str = ""
    scope: str = ""
    #: Providers that return the user to a POST rather than a GET. Apple does
    #: this when the scope asks for name or email (`response_mode=form_post`).
    posts_back: bool = False
    #: OIDC providers accept PKCE; GitHub's plain OAuth2 ignores the extra
    #: parameters, so it is sent to everyone and required of no one.
    uses_pkce: bool = True

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self._client_secret = client_secret

    @property
    def configured(self) -> bool:
        """Whether this provider has credentials to use.

        The frontend asks for the configured list and shows only those
        buttons. A button that leads to a provider error page is worse than
        no button: it reads as the product being broken.
        """
        return bool(self.client_id and self._client_secret)

    def client_secret(self) -> str:
        """The secret to send to the token endpoint.

        A method, not the attribute, because Apple's is not a stored string:
        it is a JWT this app signs, and it expires.
        """
        return self._client_secret

    def authorize_params(self, *, redirect_uri: str, state: str,
                         code_challenge: str) -> dict[str, str]:
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": self.scope,
            "state": state,
        }
        if self.uses_pkce:
            params["code_challenge"] = code_challenge
            params["code_challenge_method"] = "S256"
        return params

    def token_params(self, *, code: str, redirect_uri: str,
                     code_verifier: str) -> dict[str, str]:
        params = {
            "client_id": self.client_id,
            "client_secret": self.client_secret(),
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }
        if self.uses_pkce:
            params["code_verifier"] = code_verifier
        return params

    @abc.abstractmethod
    def identity(self, token_response: dict, client: httpx.Client) -> Identity:
        """Who the code belonged to.

        Given the token endpoint's response, and an HTTP client for providers
        that need a second call. Raises `IdentityError` when the provider
        answers with something this app will not act on — most importantly an
        address it has not verified.
        """


class IdentityError(Exception):
    """The provider answered, but not with an identity worth trusting."""
