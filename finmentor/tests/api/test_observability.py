"""Structured logs and request correlation.

An access log already existed, with a duration and redacted query params. The
gaps were narrower than "no observability" and more specific:

- it was a formatted sentence, so nothing could be queried;
- it logged the concrete path, so `/api/goals/7` and `/api/goals/8` were
  different keys and a record id went into the log on the way;
- `request_id` was minted inside the error handlers, so a request that
  *worked* had no id anywhere, and neither did any other log line emitted
  while it was being served.

These cover the three.
"""
from __future__ import annotations

import json
import logging

import pytest

from app.core import logging as app_logging
from app.core.config import settings
from app.core.logging import (
    SECRET_MASK, JsonFormatter, configure_logging, request_id_var,
)


@pytest.fixture
def json_logs(monkeypatch):
    monkeypatch.setattr(settings, "log_format", "json")
    configure_logging()
    yield
    monkeypatch.setattr(settings, "log_format", "text")
    configure_logging()


def api_lines(caplog) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == "finmentor.api"]


def http_record(caplog) -> logging.LogRecord:
    """The access-log record for the last request, by its `event` field.

    The last rather than the only one: some of these tests sign up first, and
    that is a request too.
    """
    records = [r for r in api_lines(caplog)
               if getattr(r, "event", None) == "http_request"]
    assert records, "no access-log line was emitted"
    return records[-1]


# --- the route template, not the path ------------------------------------

def test_the_log_carries_the_route_template_not_the_value(client, caplog):
    """`/api/learn/budgeting` and `/api/learn/compounding` must be one key.

    Logging the concrete path is what turns an access log into a pile nobody
    can aggregate, and on a route whose parameter is a record id it writes
    that id into the log as a side effect.
    """
    with caplog.at_level(logging.INFO, logger="finmentor.api"):
        response = client.get("/api/learn/budgeting")

    assert response.status_code == 200
    record = http_record(caplog)
    assert record.route == "/api/learn/{key}"
    assert "budgeting" not in record.getMessage()


def test_two_values_on_one_route_log_as_one_key(client, caplog):
    with caplog.at_level(logging.INFO, logger="finmentor.api"):
        client.get("/api/learn/budgeting")
        client.get("/api/learn/compounding")

    routes = [r.route for r in api_lines(caplog)
              if getattr(r, "event", None) == "http_request"]
    assert routes == ["/api/learn/{key}", "/api/learn/{key}"]


def test_an_unmatched_path_still_says_what_was_asked_for(client, caplog):
    """A 404 has no route to name, and the path is the only useful thing."""
    with caplog.at_level(logging.INFO, logger="finmentor.api"):
        client.get("/api/no-such-thing")

    assert http_record(caplog).route == "/api/no-such-thing"


def test_the_structured_fields_are_present_and_typed(client, caplog):
    with caplog.at_level(logging.INFO, logger="finmentor.api"):
        client.get("/healthz")

    record = http_record(caplog)
    assert record.method == "GET"
    assert record.status == 200
    assert isinstance(record.duration_ms, float)


# --- the request id ------------------------------------------------------

def test_a_successful_request_gets_an_id_in_the_header(client):
    """It was on the three error bodies already. The half nobody notices is a
    user describing a request that worked and nobody being able to find it."""
    response = client.get("/healthz")

    rid = response.headers["X-Request-ID"]
    assert len(rid) == 8 and all(c in "0123456789abcdef" for c in rid)


def test_the_header_and_the_log_line_agree(client, caplog):
    with caplog.at_level(logging.INFO, logger="finmentor.api"):
        response = client.get("/healthz")

    assert http_record(caplog).request_id == response.headers["X-Request-ID"]


def test_an_error_body_and_the_log_line_agree(client, caplog):
    """Two ids for one request is worse than either: the body quotes one
    number, the log holds another, and neither finds the other."""
    with caplog.at_level(logging.INFO, logger="finmentor.api"):
        response = client.get("/api/no-such-thing")

    body_rid = response.json()["error"]["request_id"]
    assert body_rid == response.headers["X-Request-ID"]
    assert http_record(caplog).request_id == body_rid


def test_a_client_supplied_id_is_honoured(client):
    """So a caller can stitch its own trace to ours."""
    response = client.get("/healthz", headers={"X-Request-ID": "abcdef12"})

    assert response.headers["X-Request-ID"] == "abcdef12"


@pytest.mark.parametrize("supplied", [
    pytest.param("../../etc/passwd", id="traversal"),
    pytest.param("a" * 500, id="very long"),
    pytest.param("not hex!", id="wrong alphabet"),
    pytest.param("ABCDEF12", id="upper case"),
    pytest.param("", id="empty"),
    pytest.param("abc\nInjected: line", id="newline injection"),
])
def test_a_malformed_client_id_is_replaced_not_trusted(client, supplied):
    """It is free-form input that gets written to a log and echoed back, so
    only the shape we generate ourselves survives."""
    response = client.get("/healthz", headers={"X-Request-ID": supplied})

    rid = response.headers["X-Request-ID"]
    assert rid != supplied
    assert len(rid) == 8 and all(c in "0123456789abcdef" for c in rid)


@pytest.fixture
def probe_route():
    """A throwaway route that reports what the request scope looks like inside.

    Added to the real app and removed afterwards, because the mechanism under
    test is the middleware and a hand-built scope would not exercise it.
    """
    from app import main as app_main

    unrelated = logging.getLogger("finmentor.engine.deep")
    seen: dict[str, object] = {}

    @app_main.app.get("/_probe")
    def _probe():
        seen["rid"] = request_id_var.get()
        unrelated.warning("something worth knowing")
        return {"ok": True}

    try:
        yield seen
    finally:
        app_main.app.router.routes = [
            route for route in app_main.app.router.routes
            if getattr(route, "path", None) != "/_probe"
        ]


def test_the_id_reaches_a_log_line_nobody_wrote_for_observability(client, probe_route,
                                                                  caplog):
    """The whole point of the context variable.

    A line emitted deep inside the request by code that knows nothing about
    requests still comes out carrying the id. Threading a parameter would
    only correlate the call sites that remembered to accept one.
    """
    with caplog.at_level(logging.WARNING, logger="finmentor.engine.deep"):
        response = client.get("/_probe")

    deep = [r for r in caplog.records if r.name == "finmentor.engine.deep"]
    assert len(deep) == 1
    assert deep[0].request_id == response.headers["X-Request-ID"]


def test_the_context_variable_is_set_during_a_request(client, probe_route):
    assert request_id_var.get() == "-", "no request is being served right now"

    response = client.get("/_probe")

    assert probe_route["rid"] == response.headers["X-Request-ID"]
    assert probe_route["rid"] != "-"


def test_the_id_is_not_leaked_between_requests(client):
    """A `ContextVar` is reset in a `finally`, so the next request starts clean."""
    first = client.get("/healthz").headers["X-Request-ID"]
    second = client.get("/healthz").headers["X-Request-ID"]

    assert first != second
    assert request_id_var.get() == "-"


# --- the caller ----------------------------------------------------------

def test_the_access_log_names_the_caller(raw_client, db, caplog):
    """Driven with a real token on `raw_client`, not `client`.

    The `client` fixture overrides `require_user`, so nothing inside it ever
    records who called -- the same blind spot that let an IDOR ship (lesson
    3). A test of a thing `require_user` does has to let `require_user` run.
    """
    signup = raw_client.post("/api/auth/signup", json={
        "email": "observed@example.com", "password": "a-long-enough-password-1",
    })
    token = signup.json()["access_token"]
    user_id = db.scalar(
        __import__("sqlalchemy").select(
            __import__("app.models.user", fromlist=["User"]).User.id
        ).where(
            __import__("app.models.user", fromlist=["User"]).User.email
            == "observed@example.com"
        )
    )

    with caplog.at_level(logging.INFO, logger="finmentor.api"):
        raw_client.get("/api/me/summary",
                       headers={"Authorization": f"Bearer {token}"})

    assert http_record(caplog).user_id == user_id


def test_an_unauthenticated_request_logs_no_user(raw_client, caplog):
    """An id in a failed attempt is a claim, not a fact. Writing it down would
    make the log assert what the request just failed to prove."""
    with caplog.at_level(logging.INFO, logger="finmentor.api"):
        raw_client.get("/api/me/summary")

    assert http_record(caplog).user_id is None


# --- the json formatter --------------------------------------------------

def test_json_output_is_one_object_per_line(json_logs, caplog):
    log = logging.getLogger("finmentor.api")
    formatter = JsonFormatter()

    with caplog.at_level(logging.INFO, logger="finmentor.api"):
        log.info("hello %s", "world", extra={"route": "/x", "status": 200})

    line = formatter.format(api_lines(caplog)[0])
    payload = json.loads(line)
    assert "\n" not in line
    assert payload["message"] == "hello world"
    assert payload["route"] == "/x"
    assert payload["status"] == 200
    assert payload["level"] == "INFO"


def test_json_output_keeps_the_readable_message(json_logs, caplog):
    """A structured line is still read by a person tailing it."""
    log = logging.getLogger("finmentor.api")

    with caplog.at_level(logging.INFO, logger="finmentor.api"):
        log.info("GET /healthz -> 200")

    payload = json.loads(JsonFormatter().format(api_lines(caplog)[0]))
    assert payload["message"] == "GET /healthz -> 200"


def test_json_output_redacts_the_message_too(json_logs, caplog):
    """Putting a value in a field instead of a sentence does not make it safe.

    The redaction rules are the same rules either way, so the formatter runs
    the message through them rather than assuming the caller did.
    """
    log = logging.getLogger("finmentor.api")

    with caplog.at_level(logging.INFO, logger="finmentor.api"):
        log.info("connecting to postgresql://finmentor:hunter2@db:5432/x")

    payload = json.loads(JsonFormatter().format(api_lines(caplog)[0]))
    assert "hunter2" not in payload["message"]
    assert SECRET_MASK in payload["message"]


def test_json_output_redacts_structured_fields(json_logs, caplog):
    log = logging.getLogger("finmentor.api")

    with caplog.at_level(logging.INFO, logger="finmentor.api"):
        log.info("saved", extra={"payload": {"password": "hunter2",
                                             "monthly_income": 4200}})

    payload = json.loads(JsonFormatter().format(api_lines(caplog)[0]))
    assert payload["payload"]["password"] == SECRET_MASK
    assert payload["payload"]["monthly_income"] != 4200


def test_json_output_carries_an_exception_as_a_field(json_logs, caplog):
    log = logging.getLogger("finmentor.api")

    with caplog.at_level(logging.ERROR, logger="finmentor.api"):
        try:
            raise ValueError("connecting to postgresql://u:hunter2@db/x")
        except ValueError:
            log.exception("it failed")

    payload = json.loads(JsonFormatter().format(api_lines(caplog)[0]))
    assert "ValueError" in payload["exception"]
    assert "hunter2" not in payload["exception"], "a traceback is text too"


def test_an_unknown_format_falls_back_rather_than_crashing(monkeypatch):
    """A typo in a deployment variable must not take the process down."""
    monkeypatch.setattr(settings, "log_format", "yaml-please")

    configure_logging()

    handler = logging.getLogger().handlers[0]
    assert not isinstance(handler.formatter, JsonFormatter)
    monkeypatch.setattr(settings, "log_format", "text")
    configure_logging()


def test_configure_logging_is_idempotent(monkeypatch):
    """It is called by the API factory, by the bot and by several tests.

    `basicConfig` is a no-op once a handler exists, which used to mean the
    second caller silently kept the first one's format.
    """
    monkeypatch.setattr(settings, "log_format", "json")
    configure_logging()
    configure_logging()

    # Not a handler count: pytest attaches several of its own, so the thing
    # worth asserting is that our formatter reached them and that the record
    # factory was not wrapped twice.
    assert any(isinstance(h.formatter, JsonFormatter)
               for h in logging.getLogger().handlers)
    factory = logging.getLogRecordFactory()
    assert getattr(factory, "_finmentor_request_id", False)
    inner = getattr(factory, "__wrapped_depth__", None)
    assert inner is None, "the factory should not stack"

    monkeypatch.setattr(settings, "log_format", "text")
    configure_logging()


def test_the_record_factory_is_not_wrapped_twice(monkeypatch):
    """Ten calls to `configure_logging` must not mean ten nested factories.

    Each wrap would add a call to every log record the process ever makes,
    and nothing would look broken until the stack got deep.
    """
    configure_logging()
    once = logging.getLogRecordFactory()
    for _ in range(5):
        configure_logging()

    assert logging.getLogRecordFactory() is once


def test_every_record_carries_a_request_id_field(json_logs, caplog):
    """Including ones emitted outside a request, where it is a dash."""
    log = logging.getLogger("finmentor.api")

    with caplog.at_level(logging.INFO, logger="finmentor.api"):
        log.info("a scheduled job ran")

    payload = json.loads(JsonFormatter().format(api_lines(caplog)[0]))
    assert payload["request_id"] == "-"
