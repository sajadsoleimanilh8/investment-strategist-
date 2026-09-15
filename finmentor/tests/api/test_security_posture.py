"""Configuration that is only wrong once.

Each of these is a setting that looks harmless in a diff and is expensive in
production: a wildcard CORS origin, a development signing key, a token written
to a log. They are cheap to assert and nobody notices them going wrong until
someone else does.
"""
import pathlib

import pytest

from app.core.config import Settings
from app.core.logging import redact, scrub_text
from app.main import create_app

APP_DIR = pathlib.Path(__file__).resolve().parents[2] / "app"


# --- CORS ----------------------------------------------------------------

def test_cors_origins_are_a_list_never_a_wildcard():
    """`*` plus credentials is the classic combination that lets any site read
    a logged-in user's data. The list is explicit so that cannot be typed."""
    app = create_app()
    cors = next(m for m in app.user_middleware if "CORS" in str(m))

    origins = cors.kwargs.get("allow_origins", [])
    assert origins, "no origins configured"
    assert "*" not in origins


def test_cors_does_not_allow_credentials():
    """Credentials are a bearer token in a header, not a cookie, so the browser
    never needs to send anything ambient — and turning this on would make a
    wildcard origin catastrophic rather than merely wrong."""
    app = create_app()
    cors = next(m for m in app.user_middleware if "CORS" in str(m))

    assert cors.kwargs.get("allow_credentials", False) is False


def test_the_demo_stack_points_cors_at_its_own_web_container():
    compose = (APP_DIR.parent / "docker-compose.yml").read_text(encoding="utf-8")

    assert "CORS_ORIGINS" in compose
    assert '"*"' not in compose.split("CORS_ORIGINS")[1].split("\n")[0]


# --- no cookies ----------------------------------------------------------

#: The one place in the app allowed to set a cookie, and why.
#:
#: Auth is otherwise a bearer token held in memory by the client, which is
#: what keeps this codebase free of cookie flags to get wrong. Third-party
#: sign-in needs one exception: the provider returns the browser by redirect,
#: and the alternative to a cookie is putting a credential in the URL the
#: browser is sent to, where it lands in history, referrers and access logs.
COOKIE_SETTERS = {"api/routes/oauth.py"}


def test_only_the_oauth_handoff_sets_a_cookie():
    setters = {
        path.relative_to(APP_DIR).as_posix()
        for path in APP_DIR.rglob("*.py")
        if "set_cookie" in path.read_text(encoding="utf-8")
    }

    assert setters == COOKIE_SETTERS, (
        f"{setters ^ COOKIE_SETTERS} changed which files set cookies. A new one "
        "needs httponly, secure and samesite, and this test needs to say so."
    )


def test_the_handoff_cookie_carries_every_flag():
    """It holds a credential for sixty seconds. Missing any one of these turns
    it into a credential the page's own scripts can read, that rides along on
    cross-site requests, or that travels in clear text."""
    source = (APP_DIR / "api" / "routes" / "oauth.py").read_text(encoding="utf-8")
    # To the closing paren at the call's own indentation, not the first one:
    # `max_age=int(...)` has parens of its own.
    call = source.split("response.set_cookie(")[1]
    call = call[: call.index("    )")]

    assert "httponly=True" in call, "the page must not be able to read it"
    assert 'samesite="lax"' in call, "it must not ride along on cross-site requests"
    assert "secure=" in call, "it must not travel in clear text over https"
    assert 'path="/api/auth/oauth"' in call, "it is for the exchange route only"
    assert "max_age=" in call, "a handoff that does not expire is a session"


# --- the signing key -----------------------------------------------------

def test_production_refuses_to_start_on_the_development_key():
    with pytest.raises(RuntimeError, match="JWT_SECRET"):
        Settings(demo_mode=False,
                 jwt_secret="dev-only-not-a-secret-please-replace-me").check_production()


def test_production_starts_with_a_real_key():
    Settings(demo_mode=False, jwt_secret="a" * 64,
             mail_transport="smtp").check_production()


# --- the mail transport --------------------------------------------------

def test_production_refuses_to_start_on_the_console_mailer():
    """The console transport logs reset links in full. That is what makes an
    offline demo possible and what makes it unusable in production: a link in
    a log is a bearer credential anybody with log access can spend."""
    with pytest.raises(RuntimeError, match="MAIL_TRANSPORT"):
        Settings(demo_mode=False, jwt_secret="a" * 64,
                 mail_transport="console").check_production()


def test_a_demo_may_keep_the_console_mailer():
    Settings(demo_mode=True, mail_transport="console").check_production()


def test_a_demo_may_keep_the_development_key():
    """The guard is about production, and a demo that needs a secret generated
    before it runs is a demo nobody runs."""
    Settings(demo_mode=True,
             jwt_secret="dev-only-not-a-secret-please-replace-me").check_production()


def test_no_real_secret_is_committed_anywhere():
    """`.env.example` documents the keys; it must never carry a usable one."""
    example = (APP_DIR.parent / ".env.example").read_text(encoding="utf-8")

    for line in example.splitlines():
        if line.startswith("JWT_SECRET="):
            assert "dev-only" in line or "replace" in line, \
                "a real-looking secret is committed in .env.example"


# --- secrets never reach a log ------------------------------------------

@pytest.mark.parametrize(
    "text,secret",
    [
        ("connect to postgresql://finmentor:hunter2@db:5432/x", "hunter2"),
        ("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.abc.def", "eyJhbGci"),
        ("api_key=sk-live-0123456789abcdef", "sk-live"),
        ("bot token 123456789:AAHfakefakefakefakefakefakefake12", "AAHfake"),
    ],
)
def test_the_scrubber_catches_each_shape_of_credential(text, secret):
    assert secret not in scrub_text(text)


def test_a_financial_figure_is_masked_in_a_structured_log():
    masked = redact({"monthly_income": 30_000_000, "telegram_id": 100_000_001})

    assert "30000000" not in str(masked)
    assert "100000001" not in str(masked)


def test_an_access_token_in_a_payload_is_masked():
    masked = redact({"access_token": "eyJhbGciOiJIUzI1NiJ9.abc.def"})

    assert "eyJhbGci" not in str(masked)
