"""Sign in with Google, GitHub or Apple.

The flow, and where each piece of it lives:

    /providers          which buttons the sign-in page should show
    /{provider}/start   redirect to the provider, carrying state and PKCE
    /{provider}/callback   the provider returns here; sets a handoff cookie
    /exchange           the frontend trades that cookie for a token pair

The last two exist as a pair rather than one redirect because of what a
redirect can carry. Putting an access token in the URL the browser is sent to
would write a credential into history, into the referrer of the next request,
and into any log that records paths. So the callback puts a 60-second,
single-purpose token in an HttpOnly cookie the page's own JavaScript cannot
read, and the page asks for its tokens over a normal request.

That cookie is `SameSite=Lax`, which is sent on the top-level navigation the
provider performs and on same-origin requests. It is *not* sent on a
cross-origin XHR, so the exchange has to be same-origin with the API — which
is how this app deploys (one origin, the API serving the built SPA) and what
the Vite dev proxy reproduces locally. A split-origin deployment needs
`SameSite=None; Secure`, which needs HTTPS on both, and that is a deployment
decision rather than a default worth shipping.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

import httpx
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

from app.api.deps import DbSession, auth_rate_limit
from app.core import security
from app.core.config import settings
from app.oauth import registry
from app.oauth.base import IdentityError, OAuthProvider
from app.repositories import identities as identities_repo
from app.schemas.auth import TokenPair

log = logging.getLogger("finmentor.api")

router = APIRouter(prefix="/api/auth/oauth", tags=["auth"])

#: Long enough for a person to read a consent screen and find their password
#: manager, short enough that an abandoned attempt cannot be resumed later.
STATE_TTL = timedelta(minutes=15)
#: The frontend asks for its tokens as soon as the page loads. A minute is
#: generous and still leaves nothing usable in a cookie jar afterwards.
HANDOFF_TTL = timedelta(seconds=60)
HANDOFF_COOKIE = "finmentor_handoff"

#: Where the SPA finishes the flow. It calls `/exchange`, then routes onward.
CALLBACK_PATH = "/auth/callback"


def _redirect_uri(provider: str) -> str:
    """What the provider was told to send the browser back to.

    Sent again at the token endpoint, where every provider checks it matches
    the first one exactly. It has to be a configured constant rather than
    something derived from the incoming request: a redirect URI taken from a
    `Host` header is a redirect URI an attacker can set.
    """
    return f"{settings.oauth_redirect_base}/api/auth/oauth/{provider}/callback"


def _require_provider(name: str) -> OAuthProvider:
    provider = registry.get(name)
    if provider is None:
        # Unknown and unconfigured answer the same: a deployment's provider
        # list is not a secret, but nor is it worth enumerating by error.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown sign-in provider")
    return provider


def _fail(reason: str) -> RedirectResponse:
    """Back to the sign-in page with a code the frontend turns into a sentence.

    A reason code, not the underlying error: what went wrong at a provider is
    for the log, and the person needs one readable sentence and a way to try
    again.
    """
    return RedirectResponse(
        f"{settings.web_base_url}/login?error={reason}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/providers")
def providers() -> dict[str, list[str]]:
    """Which sign-in buttons to draw. Public: it is a property of the build."""
    return {"providers": registry.available()}


@router.get("/{provider_name}/start")
def start(provider_name: str, next: str = "/dashboard") -> RedirectResponse:
    """Send the browser to the provider, carrying state and a PKCE challenge.

    `state` is a signed, expiring payload rather than a row in a table: it has
    to survive a round trip through someone else's site, and signing it means
    a callback this app did not start will not verify. The PKCE verifier rides
    inside it, which is why it must be signed rather than merely random.
    """
    provider = _require_provider(provider_name)
    verifier, challenge = security.pkce_pair()
    state = security.sign_payload(
        # `next` is checked on the way out, not trusted on the way back: an
        # open redirect is one of the few ways a sign-in flow becomes a
        # phishing tool.
        {"p": provider.name, "v": verifier, "next": _safe_next(next)},
        kind=security.STATE,
        lifetime=STATE_TTL,
    )
    params = provider.authorize_params(
        redirect_uri=_redirect_uri(provider.name),
        state=state,
        code_challenge=challenge,
    )
    return RedirectResponse(
        f"{provider.authorize_url}?{httpx.QueryParams(params)}",
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )


def _safe_next(next: str) -> str:
    """A path inside this app, or the dashboard.

    Anything with a scheme or a host is refused: `?next=https://elsewhere` is
    how a trusted sign-in link becomes a redirect to somebody else's copy of
    the login page.
    """
    if not next.startswith("/") or next.startswith("//"):
        return "/dashboard"
    return next


@router.api_route("/{provider_name}/callback", methods=["GET", "POST"])
async def callback(provider_name: str, request: Request, db: DbSession,
                   _: None = Depends(auth_rate_limit)) -> RedirectResponse:
    """Where the provider sends the browser back.

    GET for Google and GitHub, POST for Apple, which switches to `form_post`
    when the scope includes email. One handler either way: the parameters are
    the same, only the envelope differs.
    """
    params = dict(request.query_params)
    if request.method == "POST":
        params.update({k: str(v) for k, v in (await request.form()).items()})

    provider = _require_provider(provider_name)

    if params.get("error"):
        # The person pressed cancel, or the provider refused. Neither is an
        # error worth a stack trace.
        log.info("oauth: %s returned %s", provider_name, params["error"])
        return _fail("cancelled")

    try:
        state = security.read_payload(params.get("state", ""), kind=security.STATE)
    except security.TokenError:
        return _fail("state")
    if state.get("p") != provider.name:
        # A state minted for one provider replayed at another's callback.
        return _fail("state")

    code = params.get("code")
    if not code:
        return _fail("state")

    # Both of the next two are synchronous and this handler is `async`, so
    # running them inline would block the event loop — the provider round trip
    # for up to ten seconds, and the database for as long as it takes. Every
    # other route in this app is a plain `def` and therefore already runs in a
    # worker thread; this one has to be `async` because Starlette's form
    # parsing is (Apple posts its callback rather than redirecting to it), so
    # it has to hand the blocking work over itself. The bot does the same thing
    # for the same reason (`asyncio.to_thread` throughout `app/bot/handlers`).
    #
    # What was at stake: one sign-in stalled every connected live-price
    # WebSocket and every other request in the process for the length of a
    # provider's response.
    try:
        identity = await asyncio.to_thread(
            _exchange_code, provider, code=code, verifier=state.get("v", ""))
    except (IdentityError, httpx.HTTPError) as exc:
        log.warning("oauth: %s sign-in failed: %s", provider_name, exc)
        return _fail("provider")

    def _resolve():
        user, created = identities_repo.resolve(
            db, provider=provider.name, subject=identity.subject, email=identity.email
        )
        db.commit()
        return user, created

    try:
        user, created = await asyncio.to_thread(_resolve)
    except identities_repo.NoAddressError:
        return _fail("no_email")
    log.info("oauth: %s signed in via %s (new account: %s)",
             user.id, provider.name, created)

    handoff = security.sign_payload(
        {"sub": str(user.id), "ver": user.token_version},
        kind=security.HANDOFF, lifetime=HANDOFF_TTL,
    )
    response = RedirectResponse(
        f"{settings.web_base_url}{CALLBACK_PATH}?next={state.get('next', '/dashboard')}",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    response.set_cookie(
        HANDOFF_COOKIE, handoff,
        max_age=int(HANDOFF_TTL.total_seconds()),
        httponly=True,                       # the page must not be able to read it
        samesite="lax",
        secure=settings.oauth_redirect_base.startswith("https"),
        path="/api/auth/oauth",              # sent to the exchange route and nowhere else
    )
    return response


def _exchange_code(provider: OAuthProvider, *, code: str, verifier: str):
    """Trade the code for a token, then ask the provider who signed in."""
    with httpx.Client(timeout=10.0) as client:
        token_response = client.post(
            provider.token_url,
            data=provider.token_params(
                code=code,
                redirect_uri=_redirect_uri(provider.name),
                code_verifier=verifier,
            ),
            headers={"Accept": "application/json"},
        )
        token_response.raise_for_status()
        return provider.identity(token_response.json(), client)


@router.post("/exchange", response_model=TokenPair)
def exchange(db: DbSession, response: Response,
             finmentor_handoff: str | None = Cookie(default=None)) -> TokenPair:
    """Trade the handoff cookie for a real token pair.

    The cookie is cleared on the way out whatever happens: it is single use by
    intent, and leaving a spent one in the jar is a credential sitting around
    for no reason.
    """
    response.delete_cookie(HANDOFF_COOKIE, path="/api/auth/oauth")

    if not finmentor_handoff:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "that sign-in has expired")
    try:
        claims = security.read_payload(finmentor_handoff, kind=security.HANDOFF)
    except security.TokenError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc))

    from app.repositories import users as users_repo
    user = users_repo.get(db, int(claims["sub"]))
    if user is None or user.token_version != claims.get("ver"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "that sign-in has expired")

    return TokenPair(
        access_token=security.create_access_token(user.id, user.token_version),
        refresh_token=security.create_refresh_token(user.id, user.token_version),
        expires_in=settings.access_token_ttl_minutes * 60,
    )
