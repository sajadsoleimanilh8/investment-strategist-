"""Tell me exactly what to paste where, and whether it took.

Registering an OAuth client is a few fields in someone else's web console, and
every one of them has to match a value in this application's configuration
exactly. The mismatches are silent in the worst way: the button works, the
consent screen appears, and the callback fails with a message from the
provider that does not mention which side is wrong.

So this prints the strings to paste, checks the ones that can be checked from
here, and says what is still missing.

    python scripts/oauth_doctor.py

It makes no network call for a provider that is not configured, and it never
prints a secret.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # run as `python scripts/...`

import httpx  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.oauth import registry  # noqa: E402

#: Where each provider's client is created, because finding the page is half
#: the work and every one of them has moved at least once.
CONSOLES = {
    "google": "https://console.cloud.google.com/apis/credentials"
              "  (Create credentials -> OAuth client ID -> Web application)",
    "github": "https://github.com/settings/developers"
              "  (OAuth Apps -> New OAuth App)",
    "apple": "https://developer.apple.com/account/resources/identifiers"
             "  (Services IDs -> your id -> Sign in with Apple -> Configure)",
}

#: What each provider needs before its button appears.
REQUIRED = {
    "google": ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"),
    "github": ("GITHUB_CLIENT_ID", "GITHUB_CLIENT_SECRET"),
    "apple": ("APPLE_CLIENT_ID", "APPLE_TEAM_ID", "APPLE_KEY_ID", "APPLE_PRIVATE_KEY"),
}


def redirect_uri(provider: str) -> str:
    return f"{settings.oauth_redirect_base}/api/auth/oauth/{provider}/callback"


def missing(provider: str) -> list[str]:
    return [key for key in REQUIRED[provider]
            if not getattr(settings, key.lower(), "")]


def check_google() -> str | None:
    """Ask Google whether it has heard of this client id.

    The discovery document is public and the token endpoint will not talk to
    us without a code, so what is checkable from here is the shape: a client
    id that is not `...apps.googleusercontent.com` is not a web client id, and
    that is the mistake that produces "The OAuth client was not found".
    """
    if not settings.google_client_id.endswith(".apps.googleusercontent.com"):
        return ("GOOGLE_CLIENT_ID does not look like a web client id "
                "(they end in .apps.googleusercontent.com)")
    try:
        discovery = httpx.get(
            "https://accounts.google.com/.well-known/openid-configuration", timeout=8)
        discovery.raise_for_status()
    except httpx.HTTPError as exc:
        return f"could not reach Google to confirm its endpoints: {exc}"
    return None


def main() -> int:
    print(f"Redirect base: {settings.oauth_redirect_base}")
    print(f"Web base:      {settings.web_base_url}")
    if settings.oauth_redirect_base == settings.web_base_url:
        print("               (one origin, which is what the handoff cookie needs)")
    else:
        print("               ! these differ, so the SPA and the API are on "
              "different origins and the handoff cookie will not be sent")
    print()

    configured = registry.available()
    for provider in REQUIRED:
        print(f"--- {provider} " + "-" * (60 - len(provider)))
        gaps = missing(provider)
        if gaps:
            print(f"  not configured. Set: {', '.join(gaps)}")
            print(f"  create one at: {CONSOLES[provider]}")
            print(f"  register this redirect URI, exactly:")
            print(f"      {redirect_uri(provider)}")
            if provider == "apple":
                print("  note: Apple rejects localhost. This one needs a real "
                      "domain with HTTPS.")
            print()
            continue

        print(f"  configured{'' if provider in configured else ', but the registry disagrees'}")
        print(f"  redirect URI it will send: {redirect_uri(provider)}")
        problem = check_google() if provider == "google" else None
        if problem:
            print(f"  ! {problem}")
        else:
            print("  nothing obviously wrong from here. The rest needs a real "
                  "sign-in through a browser.")
        print()

    print("Buttons the sign-in page will show:", configured or "none")
    return 0


if __name__ == "__main__":
    sys.exit(main())
