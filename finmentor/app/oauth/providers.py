"""The three providers.

Google and Apple are OpenID Connect: the token response already contains an id
token that says who signed in, so there is no second call. GitHub is plain
OAuth2 and needs one — and then a second one, because a GitHub user's primary
address is not in the profile payload unless they made it public.

The recurring theme is verified addresses. Every provider here will happily
report an address the account holder has never proved they control, and an
unverified address is not an identity: matching one against an existing
FinMentor account would let anybody who can type take over that account.
"""
from __future__ import annotations

import time
from datetime import timedelta

import httpx
import jwt
from jwt import PyJWKClient

from app.core.config import settings
from app.oauth.base import Identity, IdentityError, OAuthProvider


class GoogleProvider(OAuthProvider):
    name = "google"
    authorize_url = "https://accounts.google.com/o/oauth2/v2/auth"
    token_url = "https://oauth2.googleapis.com/token"
    scope = "openid email"
    jwks_url = "https://www.googleapis.com/oauth2/v3/certs"
    issuers = ("https://accounts.google.com", "accounts.google.com")

    def identity(self, token_response: dict, client: httpx.Client) -> Identity:
        claims = verify_id_token(
            token_response.get("id_token", ""),
            jwks_url=self.jwks_url,
            audience=self.client_id,
            issuers=self.issuers,
        )
        if not claims.get("email_verified"):
            raise IdentityError("Google has not verified that address")
        return Identity(subject=str(claims["sub"]), email=claims.get("email"))


class AppleProvider(OAuthProvider):
    """Sign in with Apple.

    Two things are unlike the others. The client secret is not a stored
    string: it is a short-lived ES256 JWT this app signs with a key downloaded
    from the developer portal, which is why `client_secret()` is overridden.
    And the callback arrives as a POST, because asking for the email scope
    switches Apple to `response_mode=form_post`.

    Apple also sends the person's name exactly once, on the first
    authorisation, and never again. This app does not ask for it and does not
    store it, so there is nothing to lose by not capturing it.
    """

    name = "apple"
    authorize_url = "https://appleid.apple.com/auth/authorize"
    token_url = "https://appleid.apple.com/auth/token"
    scope = "email"
    jwks_url = "https://appleid.apple.com/auth/keys"
    issuers = ("https://appleid.apple.com",)
    posts_back = True

    @property
    def configured(self) -> bool:
        return bool(
            self.client_id
            and settings.apple_team_id
            and settings.apple_key_id
            and settings.apple_private_key
        )

    def client_secret(self) -> str:
        """A JWT signed with the .p8 key, valid for six months at most.

        Apple's own ceiling. Minted per request rather than cached: it costs
        one signature, and a cached one is a thing that expires quietly at
        3am six months after the last deploy.
        """
        now = int(time.time())
        return jwt.encode(
            {
                "iss": settings.apple_team_id,
                "iat": now,
                "exp": now + int(timedelta(days=180).total_seconds()),
                "aud": "https://appleid.apple.com",
                "sub": self.client_id,
            },
            settings.apple_private_key.replace("\\n", "\n"),
            algorithm="ES256",
            headers={"kid": settings.apple_key_id},
        )

    def authorize_params(self, **kwargs) -> dict[str, str]:
        params = super().authorize_params(**kwargs)
        # Without this Apple redirects with a GET and no email at all.
        params["response_mode"] = "form_post"
        return params

    def identity(self, token_response: dict, client: httpx.Client) -> Identity:
        claims = verify_id_token(
            token_response.get("id_token", ""),
            jwks_url=self.jwks_url,
            audience=self.client_id,
            issuers=self.issuers,
        )
        # Apple sends `email_verified` as a string on some paths and a bool on
        # others, and omits it for a private relay address (which is verified
        # by construction: Apple owns the domain and forwards the mail).
        verified = claims.get("email_verified")
        if verified not in (True, "true", None):
            raise IdentityError("Apple has not verified that address")
        return Identity(subject=str(claims["sub"]), email=claims.get("email"))


class GitHubProvider(OAuthProvider):
    name = "github"
    authorize_url = "https://github.com/login/oauth/authorize"
    token_url = "https://github.com/login/oauth/access_token"
    scope = "read:user user:email"
    uses_pkce = False           # plain OAuth2; the extra parameters are ignored

    def identity(self, token_response: dict, client: httpx.Client) -> Identity:
        token = token_response.get("access_token")
        if not token:
            raise IdentityError("GitHub returned no access token")
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }

        profile = client.get("https://api.github.com/user", headers=headers)
        profile.raise_for_status()
        subject = profile.json().get("id")
        if subject is None:
            raise IdentityError("GitHub returned no account id")

        # The profile's `email` is whatever the person made public, which is
        # often nothing and is never guaranteed verified. The addresses
        # endpoint is the only place the truth is.
        addresses = client.get("https://api.github.com/user/emails", headers=headers)
        addresses.raise_for_status()
        email = next(
            (row["email"] for row in addresses.json()
             if row.get("primary") and row.get("verified")),
            None,
        )
        return Identity(subject=str(subject), email=email)


def verify_id_token(token: str, *, jwks_url: str, audience: str,
                    issuers: tuple[str, ...]) -> dict:
    """Decode an OIDC id token, verifying signature, audience and issuer.

    All three matter. Without the signature check the token is a suggestion.
    Without the audience check a token minted for a different application is
    accepted here, which is how one app's users become another app's. Without
    the issuer check, any signer whose key the JWKS endpoint serves will do.

    The JWKS fetch is a network call, and that is the point: the keys rotate.
    `PyJWKClient` caches them, so it is not a call per sign-in.
    """
    if not token:
        raise IdentityError("the provider returned no id token")
    try:
        signing_key = _jwks(jwks_url).get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=audience,
            issuer=list(issuers),
        )
    except jwt.PyJWTError as exc:
        raise IdentityError(f"the provider's id token did not verify: {exc}") from exc


_jwks_clients: dict[str, PyJWKClient] = {}


def _jwks(url: str) -> PyJWKClient:
    if url not in _jwks_clients:
        _jwks_clients[url] = PyJWKClient(url, cache_keys=True)
    return _jwks_clients[url]
