"""The error shape, and what it refuses to say.

Two jobs. A client should have exactly one body to parse whatever goes wrong,
and a 500 should tell an attacker nothing — an unhandled exception's message is
untrusted text that may carry a connection string, a token, or somebody's
balance.

The secrets planted below are fake but shaped like the real thing, because the
point is to assert they do not appear in the response.
"""
import pytest
from fastapi import HTTPException

from app.api import errors
from app.main import app as fastapi_app

DSN = "postgresql://finmentor:hunter2@db:5432/finmentor"
TOKEN = "Bearer sk-live-abcdef0123456789abcdef"


@pytest.fixture
def boom(raw_client):
    """A route that raises whatever a test hands it.

    Added to the real app so the real handlers run. `raise_server_exceptions`
    is off, or TestClient re-raises instead of letting the handler respond —
    which would test nothing.
    """
    from fastapi.testclient import TestClient

    holder = {}

    @fastapi_app.get("/__boom")
    def explode():
        raise holder["error"]

    client = TestClient(fastapi_app, raise_server_exceptions=False)

    def trigger(error: Exception):
        holder["error"] = error
        return client.get("/__boom")

    yield trigger

    fastapi_app.router.routes = [
        route for route in fastapi_app.router.routes
        if getattr(route, "path", None) != "/__boom"
    ]


# --- the shape -----------------------------------------------------------

def test_every_error_has_the_same_envelope(raw_client):
    response = raw_client.get("/api/users/999999")

    body = response.json()
    assert set(body) == {"error"}
    assert set(body["error"]) >= {"code", "message", "request_id"}


@pytest.mark.parametrize(
    "path,expected_status,expected_code",
    [
        ("/api/nope", 404, "not_found"),
        ("/api/users/1", 401, "unauthenticated"),
    ],
)
def test_the_code_is_stable_and_branchable(raw_client, path, expected_status, expected_code):
    response = raw_client.get(path)

    assert response.status_code == expected_status
    assert response.json()["error"]["code"] == expected_code


def test_a_422_carries_field_level_detail_a_form_can_show(raw_client):
    response = raw_client.post("/api/auth/signup",
                               json={"email": "not-an-email", "password": "short"})

    assert response.status_code == 422
    fields = {item["field"] for item in response.json()["error"]["fields"]}
    assert "email" in fields and "password" in fields


def test_a_422_never_echoes_the_rejected_password(raw_client):
    """Pydantic's raw errors include the rejected `input`. For a signup that is
    the password, and echoing it would write it into the client's console."""
    response = raw_client.post("/api/auth/signup",
                               json={"email": "a@b.co", "password": "hunter2"})

    assert "hunter2" not in response.text


def test_the_request_id_is_in_the_body_and_the_header(raw_client):
    response = raw_client.get("/api/users/1")

    assert response.headers["X-Request-ID"] == response.json()["error"]["request_id"]


def test_each_request_gets_its_own_id(raw_client):
    first = raw_client.get("/api/users/1").json()["error"]["request_id"]
    second = raw_client.get("/api/users/1").json()["error"]["request_id"]

    assert first != second


def test_a_401_keeps_its_www_authenticate_header(raw_client):
    """The header is how a client tells "log in" from "not allowed". The
    handler rebuilds the response, so it has to carry the original headers."""
    response = raw_client.get("/api/users/1")

    assert response.headers.get("WWW-Authenticate") == "Bearer"


# --- what a 500 refuses to say -------------------------------------------

def test_an_unhandled_exception_is_a_500_with_a_fixed_message(boom):
    response = boom(RuntimeError("the widget frobnicator exploded"))

    assert response.status_code == 500
    assert response.json()["error"]["message"] == errors.UNEXPECTED


def test_a_500_never_leaks_the_exception_text(boom):
    response = boom(RuntimeError("row for user 41 has balance 12345678"))

    assert "12345678" not in response.text
    assert "frobnicator" not in response.text
    assert "41" not in response.json()["error"]["message"]


def test_a_500_never_leaks_a_connection_string(boom):
    response = boom(ConnectionError(f"could not connect to {DSN}"))

    assert "hunter2" not in response.text
    assert "postgresql://" not in response.text


def test_a_500_never_leaks_a_token(boom):
    response = boom(PermissionError(f"upstream rejected {TOKEN}"))

    assert "sk-live" not in response.text


def test_a_500_never_leaks_a_traceback(boom):
    def inner():
        raise ValueError("deep")

    try:
        inner()
    except ValueError as caught:
        response = boom(caught)

    assert "Traceback" not in response.text
    assert "test_errors.py" not in response.text
    assert "File \"" not in response.text


def test_a_500_still_carries_a_request_id_to_quote(boom):
    response = boom(RuntimeError("anything"))

    assert len(response.json()["error"]["request_id"]) == 8


def test_the_real_failure_is_logged_server_side(boom, caplog):
    """The user gets nothing; whoever is on call gets the type and the path."""
    with caplog.at_level("ERROR", logger="finmentor.api"):
        boom(RuntimeError("the widget frobnicator exploded"))

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "RuntimeError" in logged
    assert "/__boom" in logged


def test_the_log_is_scrubbed_too(boom, caplog):
    """A DSN is a credential wherever it is written, including our own logs."""
    with caplog.at_level("ERROR", logger="finmentor.api"):
        boom(ConnectionError(f"could not connect to {DSN}"))

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "hunter2" not in logged


# --- the handlers do not swallow the ordinary --------------------------

def test_a_successful_request_is_untouched(raw_client):
    response = raw_client.get("/healthz")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_a_deliberate_4xx_keeps_its_own_message(raw_client, db):
    """Ours to write, and actionable — so unlike a 500 it says what happened."""
    raw_client.post("/api/auth/signup",
                    json={"email": "taken@example.com", "password": "a-long-password"})
    response = raw_client.post("/api/auth/signup",
                               json={"email": "taken@example.com", "password": "a-long-password"})

    assert response.status_code == 409
    assert "already registered" in response.json()["error"]["message"]


def test_an_http_exception_detail_is_scrubbed_on_the_way_out():
    """`detail` is sometimes built from request data, which is how a secret
    gets echoed back to whoever sent it."""
    from app.core.logging import scrub_text

    detail = f"upstream said: {DSN}"
    assert "hunter2" not in scrub_text(str(HTTPException(502, detail).detail))


# --- the constant that only exists in a newer Starlette -------------------

def test_the_validation_handler_avoids_version_fragile_status_constants():
    """`HTTP_422_UNPROCESSABLE_CONTENT` is a newer Starlette name. The pinned
    FastAPI ships a Starlette without it, so referencing it raised an
    AttributeError *inside the exception handler* — every validation error in
    the shipped container became a 500, and the whole field-level 422 body was
    dead code there.

    Nothing caught it because the local environment runs a newer FastAPI than
    requirements.txt pins. The literal is version-proof; the name is not.
    """
    import pathlib

    # The whole package, not just errors.py: the first version of this guard
    # checked one file and three other call sites went on raising the same
    # AttributeError.
    app = pathlib.Path(__file__).resolve().parents[2] / "app"
    offenders = {
        path.relative_to(app).as_posix(): name
        for path in app.rglob("*.py")
        for name in ("HTTP_422_UNPROCESSABLE_CONTENT", "HTTP_422_UNPROCESSABLE_ENTITY")
        if name in path.read_text(encoding="utf-8")
    }

    assert offenders == {}, (
        f"{offenders}: ..._CONTENT does not exist in the pinned Starlette and "
        "..._ENTITY is deprecated in the newer one. The literal 422 is correct "
        "in both."
    )


def test_an_invalid_body_is_a_422_not_a_500(raw_client):
    """The behaviour the constant broke: a bad email is a validation error the
    form can act on, not a server failure."""
    response = raw_client.post("/api/auth/signup",
                               json={"email": "not-an-email", "password": "short"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
