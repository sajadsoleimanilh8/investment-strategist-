"""Which providers this deployment actually has credentials for."""
from __future__ import annotations

from app.core.config import settings
from app.oauth.base import OAuthProvider
from app.oauth.providers import AppleProvider, GitHubProvider, GoogleProvider


def _all() -> dict[str, OAuthProvider]:
    return {
        "google": GoogleProvider(settings.google_client_id, settings.google_client_secret),
        "github": GitHubProvider(settings.github_client_id, settings.github_client_secret),
        # Apple's "secret" is signed from a key file; `configured` on that
        # class checks the parts that actually matter.
        "apple": AppleProvider(settings.apple_client_id, ""),
    }


def available() -> list[str]:
    """The providers with credentials, in a stable order.

    The frontend renders a button per name and nothing else. A provider
    without credentials is absent rather than disabled: a button that leads to
    the provider's own error page reads as this product being broken, and it
    is a support ticket nobody can answer.
    """
    return [name for name, provider in _all().items() if provider.configured]


def get(name: str) -> OAuthProvider | None:
    """The provider, or None for an unknown or unconfigured one.

    One answer for both, because the caller turns both into the same 404: a
    deployment's provider list is not a secret, but nor is it something to
    enumerate through error messages.
    """
    provider = _all().get(name)
    return provider if provider is not None and provider.configured else None
