"""Starting the bot on a link that drops packets.

It did not survive one. `run_polling` calls `getMe` during initialisation,
PTB's default timeouts are 5s, and the first real start of this bot measured
`getMe` at anywhere from 1.6s to a TLS handshake timeout. The process exited
with `TimedOut` before it had polled once.
"""
from __future__ import annotations

import pytest
from telegram.error import NetworkError, TimedOut

from app.bot import main as bot_main
from app.core.config import settings


class FakeApp:
    def __init__(self, outcomes: list):
        self.outcomes = outcomes

    def run_polling(self):
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome


@pytest.fixture
def no_sleep(monkeypatch):
    waits: list[float] = []
    monkeypatch.setattr(bot_main.time, "sleep", waits.append)
    monkeypatch.setattr(bot_main, "configure_logging", lambda: None)
    return waits


def run_with(monkeypatch, outcomes: list) -> list:
    built: list = []

    def build():
        app = FakeApp(outcomes)
        built.append(app)
        return app

    monkeypatch.setattr(bot_main, "build_app", build)
    bot_main.main()
    return built


def test_a_timeout_at_startup_is_retried(monkeypatch, no_sleep):
    built = run_with(monkeypatch, [TimedOut(), TimedOut(), None])

    assert len(built) == 3
    assert len(no_sleep) == 2


def test_a_network_error_at_startup_is_retried(monkeypatch, no_sleep):
    built = run_with(monkeypatch, [NetworkError("handshake timed out"), None])

    assert len(built) == 2


def test_it_gives_up_after_the_configured_attempts(monkeypatch, no_sleep):
    monkeypatch.setattr(settings, "telegram_startup_attempts", 3)

    with pytest.raises(TimedOut):
        run_with(monkeypatch, [TimedOut(), TimedOut(), TimedOut()])

    assert len(no_sleep) == 2, "no wait after the last attempt"


def test_a_programming_error_is_not_retried(monkeypatch, no_sleep):
    """Retrying a bug five times only delays the traceback."""
    with pytest.raises(ValueError):
        run_with(monkeypatch, [ValueError("bad handler"), None])

    assert no_sleep == []


def test_the_waits_back_off_and_are_bounded(monkeypatch, no_sleep):
    monkeypatch.setattr(settings, "telegram_startup_attempts", 20)
    run_with(monkeypatch, [TimedOut()] * 19 + [None])

    assert no_sleep == sorted(no_sleep)
    assert max(no_sleep) <= 60


def test_the_client_is_built_with_the_configured_timeout(monkeypatch):
    monkeypatch.setattr(settings, "telegram_timeout_seconds", 42.0)

    app = bot_main.build_app()

    assert "42.0" in repr(app.bot.request._client_kwargs.get("timeout"))
