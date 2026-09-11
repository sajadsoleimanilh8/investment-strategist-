"""What Telegram sees when something breaks.

A traceback in a chat window is both a bad apology and a disclosure — the text
of an exception routinely carries a connection string, a user id, or a row of
someone's finances. So there are two properties worth pinning:

* every handler lets a failure *reach* the error handler rather than swallowing
  it into a silent no-reply, which looks to the user like the bot ignoring them
* the error handler itself says one friendly sentence and logs the rest,
  scrubbed

The first is the one that rots quietly. A `try/except` added later to "fix" a
crash turns a loud failure into an invisible one, and this is what notices.
"""
import inspect
import logging

import pytest

from app.bot import handlers, main as bot_main, messages
from tests.unit.test_onboarding import FakeContext, FakeUpdate

DSN = "postgresql://finmentor:hunter2@db:5432/finmentor"

#: Every command the bot registers, and the module-level function each one
#: calls to do its blocking work. Breaking that function is how a database or
#: engine failure is simulated without breaking anything else.
COMMAND_WORKERS = {
    "send_health": "_health_payload",
    "profile": "_profile_payload",
    "budget": "_budget_payload",
    "goals": "_goals_payload",
    "market": "_market_payload",
    "watchlist": "_watchlist_keyboard",
}


@pytest.fixture
def replies():
    return []


@pytest.fixture
def ctx():
    return FakeContext()


@pytest.fixture
def chat_stub(monkeypatch):
    class Chat:
        async def send_action(self, *args, **kwargs):
            return True

    original = FakeUpdate.__init__

    def patched(self, sink, **kwargs):
        original(self, sink, **kwargs)
        self.effective_chat = Chat()

    monkeypatch.setattr(FakeUpdate, "__init__", patched)


@pytest.fixture
def onboarded(bot_db, monkeypatch, chat_stub):
    from scripts.seed_demo_user import seed_demo_user

    monkeypatch.setattr("app.repositories.profiles.current_period", lambda *a, **k: "2026-09")
    with bot_db() as db:
        user_id = seed_demo_user(db, period="2026-09")
        db.commit()
    return user_id


def msg(replies, text=""):
    return FakeUpdate(replies, text=text, telegram_id=100_000_001)


# --- the error handler ---------------------------------------------------

@pytest.mark.asyncio
async def test_the_user_gets_one_plain_sentence(replies, ctx, chat_stub):
    class Failed(FakeContext):
        error = RuntimeError("the widget frobnicator exploded")

    await handlers.on_error(msg(replies), Failed())

    assert replies == [messages.SOMETHING_WENT_WRONG]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "secret,marker",
    [
        (RuntimeError(f"could not connect to {DSN}"), "hunter2"),
        (RuntimeError("balance for user 41 is 12,345,678"), "12,345,678"),
        (RuntimeError("token 123456789:AAHfakefakefakefakefakefakefake12"), "AAHfake"),
    ],
)
async def test_nothing_from_the_exception_reaches_the_chat(
    replies, ctx, chat_stub, secret, marker
):
    class Failed(FakeContext):
        error = secret

    await handlers.on_error(msg(replies), Failed())

    assert marker not in "".join(replies)
    assert "Traceback" not in "".join(replies)


@pytest.mark.asyncio
async def test_the_real_failure_is_logged(replies, ctx, chat_stub, caplog):
    class Failed(FakeContext):
        error = RuntimeError("the widget frobnicator exploded")

    with caplog.at_level(logging.ERROR, logger="finmentor.bot"):
        await handlers.on_error(msg(replies), Failed())

    assert "frobnicator" in "\n".join(r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_the_log_is_scrubbed(replies, ctx, chat_stub, caplog):
    """A DSN is a credential wherever it is written, our own logs included."""
    class Failed(FakeContext):
        error = RuntimeError(f"could not connect to {DSN}")

    with caplog.at_level(logging.ERROR, logger="finmentor.bot"):
        await handlers.on_error(msg(replies), Failed())

    assert "hunter2" not in "\n".join(r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_it_survives_a_chat_it_can_no_longer_reply_to(ctx):
    """Blocked bot, deleted chat. The handler must not raise from inside the
    handler that exists to stop things raising."""
    class Dead:
        async def reply_text(self, *args, **kwargs):
            raise RuntimeError("chat not found")

    class DeadUpdate:
        effective_message = Dead()

    class Failed(FakeContext):
        error = ValueError("boom")

    await handlers.on_error(DeadUpdate(), Failed())


@pytest.mark.asyncio
async def test_it_copes_with_an_update_that_is_not_an_update(ctx):
    """PTB types this parameter `object`; a timer job failing passes something
    with no message at all."""
    class Failed(FakeContext):
        error = ValueError("boom")

    await handlers.on_error(object(), Failed())


# --- failures actually reach it -----------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize("command,worker", sorted(COMMAND_WORKERS.items()))
async def test_a_broken_engine_propagates_instead_of_going_quiet(
    onboarded, replies, ctx, monkeypatch, command, worker
):
    """The handler must not swallow the failure.

    PTB's registered error handler is what turns an exception into the friendly
    message, and it only runs if the exception escapes. A handler that catches
    everything and returns leaves the user staring at a chat where their
    command simply did nothing.
    """
    def explode(*args, **kwargs):
        raise RuntimeError("database is on fire")

    monkeypatch.setattr(handlers, worker, explode)

    with pytest.raises(RuntimeError):
        await getattr(handlers, command)(msg(replies), ctx)


@pytest.mark.asyncio
async def test_a_broken_ask_propagates_too(onboarded, replies, ctx, monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("the model host vanished")

    monkeypatch.setattr(handlers, "_ask_payload", explode)
    ctx.args = ["how", "am", "I", "doing?"]

    with pytest.raises(RuntimeError):
        await handlers.ask(msg(replies), ctx)


@pytest.mark.asyncio
async def test_a_broken_callback_propagates_too(onboarded, replies, ctx, monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("database is on fire")

    monkeypatch.setattr(handlers, "_health_payload", explode)

    with pytest.raises(RuntimeError):
        await handlers.on_callback(
            FakeUpdate(replies, data="menu:health", telegram_id=100_000_001), ctx)


# --- the wiring ----------------------------------------------------------

def test_the_error_handler_is_registered(monkeypatch):
    """All of the above is theatre if nothing is listening."""
    monkeypatch.setattr("app.core.config.settings.telegram_bot_token", "123:fake")
    app = bot_main.build_app()

    assert handlers.on_error in app.error_handlers


def test_no_handler_swallows_a_bare_exception():
    """A `except Exception: pass` anywhere in the module would make the error
    handler unreachable from that path. `on_error` itself is allowed one, for
    the chat it can no longer reply to."""
    source = inspect.getsource(handlers)
    offenders = [
        line.strip() for line in source.splitlines()
        if line.strip() in {"except Exception:", "except BaseException:"}
    ]

    assert len(offenders) <= 1, f"broad excepts in handlers.py: {offenders}"


def test_the_friendly_message_says_nothing_about_the_cause():
    assert "error" not in messages.SOMETHING_WENT_WRONG.lower()
    assert "exception" not in messages.SOMETHING_WENT_WRONG.lower()
    assert messages.SOMETHING_WENT_WRONG.strip()
