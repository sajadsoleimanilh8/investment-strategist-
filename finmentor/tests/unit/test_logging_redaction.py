"""Spec section 26: no token, key, identifier, or raw figure reaches the logs."""
import json
import logging

from app.core.logging import AMOUNT_MASK, ID_MASK, SECRET_MASK, configure_logging, redact, safe_json


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
