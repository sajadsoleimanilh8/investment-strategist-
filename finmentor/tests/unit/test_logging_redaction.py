"""Spec section 26: no token, key, identifier, or raw figure reaches the logs."""
import json
import logging

import pytest

from app.core.logging import (
    AMOUNT_MASK, ID_MASK, SECRET_MASK, configure_logging, redact, safe_json,
    scrub_text,
)


def test_credentials_are_masked_whatever_the_key_is_called():
    out = redact({
        "TELEGRAM_BOT_TOKEN": "123:abc",
        "remote_llm_api_key": "sk-live",
        "Authorization": "Bearer x",
        "password": "hunter2",
        "session_id": "s-1",
    })
    assert set(out.values()) == {SECRET_MASK}


def test_financial_figures_are_masked():
    out = redact({
        "monthly_income": 30_000_000,
        "current_savings": 45_000_000,
        "target_amount": 60_000_000,
        "debt": 10_000_000,
    })
    assert set(out.values()) == {AMOUNT_MASK}


def test_expense_breakdowns_are_masked_through_their_container():
    out = redact({"expenses": {"housing": 8_000_000, "food": 5_000_000}})
    assert out["expenses"] == {"housing": AMOUNT_MASK, "food": AMOUNT_MASK}


def test_identifiers_are_masked():
    assert redact({"telegram_id": 555})["telegram_id"] == ID_MASK


def test_nested_and_list_payloads_are_walked():
    out = redact({"goals": [{"name": "laptop", "target_amount": 60_000_000, "priority": 1}]})
    goal = out["goals"][0]
    assert goal["name"] == "laptop"          # non-sensitive fields survive
    assert goal["priority"] == 1
    assert goal["target_amount"] == AMOUNT_MASK


def test_harmless_values_are_untouched():
    payload = {"locale": "fa", "is_essential": True, "period": "2026-09", "status": "ok"}
    assert redact(payload) == payload


def test_deep_structures_are_truncated_not_recursed_forever():
    payload = current = {}
    for _ in range(20):
        current["next"] = {}
        current = current["next"]
    assert "<truncated>" in json.dumps(redact(payload))


def test_safe_json_is_serialisable_and_keeps_names_readable():
    text = safe_json({"name": "Laptop", "target_amount": 60_000_000})
    assert "Laptop" in text
    assert json.loads(text)["target_amount"] == AMOUNT_MASK


def test_request_logging_never_carries_a_body(client, caplog):
    configure_logging()
    with caplog.at_level(logging.INFO, logger="finmentor.api"):
        client.post("/api/users", json={"telegram_id": 555_900, "locale": "fa"})

    messages = [r.getMessage() for r in caplog.records if r.name == "finmentor.api"]
    assert any("POST /api/users -> 201" in m for m in messages)
    assert not any("555900" in m or "telegram_id" in m for m in messages)


def test_query_parameters_are_redacted_in_the_access_log(client, caplog):
    configure_logging()
    with caplog.at_level(logging.INFO, logger="finmentor.api"):
        client.get("/healthz?token=secret-value&amount=30000000")

    logged = " ".join(r.getMessage() for r in caplog.records if r.name == "finmentor.api")
    assert "secret-value" not in logged
    assert "30000000" not in logged
    assert SECRET_MASK in logged


# --- credentials inside free text ---------------------------------------
#
# `redact` is key-driven, which used to mean a bare string sailed through it
# untouched. The bot's error handler logs `str(exception)`, and a failed
# connection quotes the DSN it failed on — password included.

def test_a_password_in_a_connection_string_is_masked():
    masked = redact("could not connect to postgresql://finmentor:hunter2@db:5432/x")

    assert "hunter2" not in masked
    assert "finmentor" in masked          # the username stays; it is useful


def test_a_bearer_token_in_a_message_is_masked():
    assert "sk-abc123def456" not in redact("Authorization: Bearer sk-abc123def456")


def test_an_api_key_assignment_is_masked():
    assert "supersecret" not in redact("api_key=supersecret failed")


def test_a_telegram_bot_token_is_masked():
    token = "123456789:AAHfakefakefakefakefakefakefakefake12"
    assert token not in redact(f"getUpdates failed for {token}")


def test_ordinary_prose_is_left_alone():
    text = "the user asked about their emergency fund"
    assert redact(text) == text


def test_strings_nested_in_a_payload_are_scrubbed_too():
    masked = redact({"detail": "dsn postgresql://u:p@h/db is unreachable"})

    assert "p@h" not in masked["detail"]


# --- the bot token in a request URL -------------------------------------
#
# The guard for this existed and never fired. `_TELEGRAM_TOKEN` began with
# `\b`, and the one place a Telegram token actually appears is the API URL --
# `https://api.telegram.org/bot<token>/getMe` -- where the digits follow the
# `t` of "bot" and so have no word boundary before them. `httpx` logs every
# request URL at INFO and PTB uses `httpx`, so starting the bot wrote its own
# live credential to the log nine times in fifteen seconds.
#
# Found by reading the log of a bot that had just been started, not by a test.

LIVE_SHAPED_TOKEN = "1234567890:AAFakeTokenForTestsOnly-not_a_real_one_0"


@pytest.mark.parametrize("line", [
    pytest.param(
        f"HTTP Request: POST https://api.telegram.org/bot{LIVE_SHAPED_TOKEN}/getMe",
        id="in a request url",
    ),
    pytest.param(
        f"https://api.telegram.org/bot{LIVE_SHAPED_TOKEN}/sendMessage?chat_id=1",
        id="url with query",
    ),
    pytest.param(LIVE_SHAPED_TOKEN, id="bare"),
    pytest.param(f"TELEGRAM_BOT_TOKEN={LIVE_SHAPED_TOKEN}", id="as a value"),
    pytest.param(f"token is {LIVE_SHAPED_TOKEN} ok", id="mid sentence"),
])
def test_a_bot_token_is_masked_wherever_it_appears(line):
    scrubbed = scrub_text(line)

    assert LIVE_SHAPED_TOKEN not in scrubbed
    assert "AAFakeTokenForTestsOnly-n" not in scrubbed, "the secret half"
    assert SECRET_MASK in scrubbed


def test_the_bot_id_may_survive_but_the_secret_may_not():
    """The numeric half is a public identifier and useful in a log; the half
    after the colon is the credential."""
    scrubbed = scrub_text(
        f"https://api.telegram.org/bot{LIVE_SHAPED_TOKEN}/getMe")

    assert "AAFakeTokenForTestsOnly-not_a_real_one_0" not in scrubbed


@pytest.mark.parametrize("line", [
    pytest.param("balance 123456789012345678901234567890", id="a long number"),
    pytest.param("ratio 12:30 and 2026-10-02T12:30:00", id="times and dates"),
    pytest.param("period 2026-09 total 4200", id="ordinary figures"),
    pytest.param("AAPL:NASDAQ", id="a ticker"),
])
def test_ordinary_text_is_not_mistaken_for_a_token(line):
    assert scrub_text(line) == line


def test_the_text_formatter_scrubs_too():
    """It did not, and text is the default.

    `JsonFormatter` scrubbed every field it emitted while the plain formatter
    scrubbed nothing, so the safer-looking output was the safe one and the
    ordinary one was not.
    """
    import logging

    from app.core.logging import TEXT_FORMAT, ScrubbingFormatter

    record = logging.LogRecord(
        "httpx", logging.INFO, __file__, 1,
        "HTTP Request: POST https://api.telegram.org/bot%s/getMe",
        (LIVE_SHAPED_TOKEN,), None,
    )
    record.request_id = "-"

    line = ScrubbingFormatter(TEXT_FORMAT).format(record)

    assert LIVE_SHAPED_TOKEN not in line
    assert SECRET_MASK in line


def test_a_credential_in_a_traceback_is_scrubbed_in_text_mode():
    import logging

    from app.core.logging import TEXT_FORMAT, ScrubbingFormatter

    try:
        raise RuntimeError(f"failed calling bot{LIVE_SHAPED_TOKEN}")
    except RuntimeError:
        import sys
        record = logging.LogRecord("x", logging.ERROR, __file__, 1, "boom",
                                   (), sys.exc_info())
    record.request_id = "-"

    line = ScrubbingFormatter(TEXT_FORMAT).format(record)

    assert LIVE_SHAPED_TOKEN not in line


def test_configure_logging_quiets_the_url_logger():
    """Defence in depth: a credential never written down cannot be leaked by
    a future formatter either, and a line per poll is noise regardless."""
    import logging

    from app.core.logging import NOISY_LOGGERS, configure_logging

    configure_logging()

    assert "httpx" in NOISY_LOGGERS
    for name in NOISY_LOGGERS:
        assert logging.getLogger(name).level >= logging.WARNING, name


# --- the one scrubbing exemption ----------------------------------------
#
# `ConsoleMailer` logs the email body in full, reset link included, because
# without a mail transport that is the only way to finish the flow offline.
# Scrubbing text output broke exactly that, so the exemption exists -- narrow,
# explicit at the call site, and guarded here against gaining a second user.

def test_the_console_mailer_body_survives_scrubbing():
    """It did not, after text-mode output started being scrubbed.

    The symptom was `?token=***` in the logged email and a password-reset
    test that could no longer find the link -- but only when it ran after a
    test that had called `configure_logging`, which is why it looked
    intermittent.
    """
    import logging

    from app.core.logging import TEXT_FORMAT, UNSCRUBBED, ScrubbingFormatter

    body = "http://localhost:5173/reset-password?token=Yl8kQ2pR7mWn4xTv"
    record = logging.LogRecord("finmentor.mail", logging.INFO, __file__, 1,
                               "email not sent (console transport)\n\n%s",
                               (body,), None)
    record.request_id = "-"
    setattr(record, UNSCRUBBED, True)

    line = ScrubbingFormatter(TEXT_FORMAT).format(record)

    assert body in line, "the dev flow needs the link intact"


def test_the_exemption_does_not_apply_without_the_marker():
    """The same body, logged by anything else, is still scrubbed."""
    import logging

    from app.core.logging import TEXT_FORMAT, ScrubbingFormatter

    record = logging.LogRecord(
        "somewhere.else", logging.INFO, __file__, 1,
        "token=Yl8kQ2pR7mWn4xTv", (), None)
    record.request_id = "-"

    line = ScrubbingFormatter(TEXT_FORMAT).format(record)

    assert "Yl8kQ2pR7mWn4xTv" not in line
    assert SECRET_MASK in line


def test_only_the_console_mailer_exempts_itself():
    """One exemption, one call site.

    A second would be a credential leak with a comment explaining why it was
    fine, which is the shape this is meant to prevent.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2]
    users = []
    for path in (root / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        # The definition itself lives in logging.py; everything else that
        # names it is a user.
        if "UNSCRUBBED" in text and path.name not in ("logging.py",):
            users.append(path.relative_to(root).as_posix())

    assert users == ["app/core/mailer.py"], users
