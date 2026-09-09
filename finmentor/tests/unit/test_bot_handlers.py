"""Command handlers and the callback router, driven with stub updates.

The point of these is the wiring, not the arithmetic: that a command reaches
the engine, that a user without a profile is asked to onboard instead of
crashing, that the callback router dispatches, and — the one that matters —
that no non-AI command ever reaches the model.
"""
import pytest

from app.bot import handlers, keyboards, messages
from app.services.education_engine import list_topics
from scripts.seed_demo_user import seed_demo_user
from scripts.seed_market_assets import seed_demo_watchlist, seed_market_assets
from tests.unit.test_onboarding import FakeContext, FakeUpdate

PERIOD = "2026-09"
DEMO_TELEGRAM_ID = 100_000_001


@pytest.fixture
def replies():
    return []


@pytest.fixture
def ctx():
    return FakeContext()


@pytest.fixture
def chat_stub(monkeypatch):
    """`send_action` needs a chat; nothing here cares what it does."""
    class Chat:
        async def send_action(self, *args, **kwargs):
            return True

    original = FakeUpdate.__init__

    def patched(self, sink, **kwargs):
        original(self, sink, **kwargs)
        self.effective_chat = Chat()

    monkeypatch.setattr(FakeUpdate, "__init__", patched)


@pytest.fixture
def demo(bot_db, monkeypatch, chat_stub):
    """The seeded demo user, reachable through the bot's own session factory."""
    monkeypatch.setattr("app.repositories.profiles.current_period", lambda *a, **k: PERIOD)
    with bot_db() as db:
        user_id = seed_demo_user(db, period=PERIOD)
        seed_market_assets(db)
        seed_demo_watchlist(db, user_id)
        db.commit()
    return user_id


def msg(replies, text=""):
    return FakeUpdate(replies, text=text, telegram_id=DEMO_TELEGRAM_ID)


def tap(replies, data):
    return FakeUpdate(replies, data=data, telegram_id=DEMO_TELEGRAM_ID)


def last(replies) -> str:
    return replies[-1]


# --- commands against a real profile ------------------------------------

@pytest.mark.asyncio
async def test_health_reports_the_engine_score(demo, replies, ctx, bot_db):
    from app.api.deps import load_twin
    from app.services.health_score import compute_health_score

    with bot_db() as db:
        expected = compute_health_score(load_twin(db, demo)).total

    await handlers.send_health(msg(replies), ctx)

    assert f"{expected:.1f}/100" in last(replies)


@pytest.mark.asyncio
async def test_profile_budget_goals_and_market_all_reply(demo, replies, ctx):
    for command in (handlers.profile, handlers.budget, handlers.goals, handlers.market):
        replies.clear()
        await command(msg(replies), ctx)
        assert replies and replies[-1].strip()


@pytest.mark.asyncio
async def test_market_carries_the_market_disclaimer(demo, replies, ctx):
    from app.schemas.market import MARKET_DISCLAIMER

    await handlers.market(msg(replies), ctx)

    assert MARKET_DISCLAIMER in last(replies)


@pytest.mark.asyncio
async def test_help_needs_no_profile_at_all(replies, ctx, chat_stub):
    await handlers.help_command(msg(replies), ctx)

    assert "/health" in last(replies)


@pytest.mark.asyncio
async def test_learn_needs_no_profile_and_lists_the_topics(replies, ctx, chat_stub):
    await handlers.learn(msg(replies), ctx)

    assert str(len(list_topics())) in last(replies)


# --- a user who has not onboarded ---------------------------------------

@pytest.mark.asyncio
async def test_start_offers_onboarding_to_a_new_user(bot_db, replies, ctx, chat_stub):
    await handlers.start(FakeUpdate(replies, text="/start", telegram_id=920_001), ctx)

    assert messages.NOT_ONBOARDED in replies


@pytest.mark.asyncio
async def test_start_shows_the_menu_to_a_returning_user(demo, replies, ctx):
    await handlers.start(msg(replies, "/start"), ctx)

    assert messages.MENU_PROMPT in replies
    assert messages.NOT_ONBOARDED not in replies


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command", [handlers.send_health, handlers.profile, handlers.budget,
                handlers.goals, handlers.market, handlers.watchlist],
)
async def test_every_data_command_asks_an_unknown_user_to_onboard(
    bot_db, replies, ctx, chat_stub, command
):
    await command(FakeUpdate(replies, text="", telegram_id=920_002), ctx)

    assert messages.NOT_ONBOARDED in replies


# --- no LLM on the deterministic commands -------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "command", [handlers.send_health, handlers.profile, handlers.budget,
                handlers.goals, handlers.market, handlers.learn, handlers.help_command],
)
async def test_no_deterministic_command_touches_the_model(
    demo, replies, ctx, monkeypatch, command
):
    """Spec section 23: only /ask and a free-text simulation may call a model."""
    def explode(*args, **kwargs):                       # pragma: no cover
        raise AssertionError("a deterministic command reached the LLM")

    monkeypatch.setattr("app.ai.synthesizer.explain", explode)
    await command(msg(replies), ctx)

    assert replies


# --- /ask ---------------------------------------------------------------

@pytest.mark.asyncio
async def test_ask_with_a_question_answers_it(demo, replies, ctx):
    ctx.args = ["why", "is", "my", "score", "what", "it", "is?"]

    await handlers.ask(msg(replies), ctx)

    assert messages.THINKING in replies
    assert len(replies) > 1


@pytest.mark.asyncio
async def test_ask_with_no_question_prompts_and_arms_the_next_message(demo, replies, ctx):
    await handlers.ask(msg(replies), ctx)

    assert messages.ASK_PROMPT in replies
    assert ctx.user_data[handlers.PENDING_KEY] == "ask"


@pytest.mark.asyncio
async def test_a_dead_local_model_still_answers_from_the_engine(demo, replies, ctx):
    from app.ai.local_llm import FakeLocalProvider
    from app.ai.safety import FINANCE_DISCLAIMER

    ctx.args = ["explain", "my", "health", "score"]
    FakeLocalProvider.unavailable = True
    try:
        await handlers.ask(msg(replies), ctx)
    finally:
        FakeLocalProvider.unavailable = False

    assert FINANCE_DISCLAIMER in last(replies)


# --- free text ----------------------------------------------------------

@pytest.mark.asyncio
async def test_a_purchase_prompt_reads_the_next_message_as_a_price(demo, replies, ctx):
    ctx.user_data[handlers.PENDING_KEY] = "purchase"

    await handlers.free_text(msg(replies, "60m"), ctx)

    assert "Savings:" in last(replies)
    assert handlers.PENDING_KEY not in ctx.user_data


@pytest.mark.asyncio
async def test_an_unreadable_price_says_so(demo, replies, ctx):
    ctx.user_data[handlers.PENDING_KEY] = "purchase"

    await handlers.free_text(msg(replies, "a nice one"), ctx)

    assert messages.UNREADABLE_AMOUNT in replies


@pytest.mark.asyncio
async def test_an_unprompted_message_is_treated_as_a_question(demo, replies, ctx):
    await handlers.free_text(msg(replies, "why is my score what it is?"), ctx)

    assert messages.THINKING in replies


# --- the callback router ------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "data",
    ["menu:home", "menu:health", "menu:finances", "menu:goals", "menu:simulate",
     "menu:market", "menu:learn", "menu:ask", "sim:whatif", "sim:purchase",
     "sim:timemachine", "learn:page:1", "learn:topic:budgeting",
     "learn:quiz:budgeting", "quiz:budgeting:1", "wl:add:BTC", "wl:remove:BTC"],
)
async def test_every_callback_is_handled(demo, replies, ctx, data):
    await handlers.on_callback(tap(replies, data), ctx)

    assert replies, f"no reply for {data}"


@pytest.mark.asyncio
async def test_an_unknown_callback_falls_back_to_the_menu(demo, replies, ctx):
    await handlers.on_callback(tap(replies, "nonsense:from:an:old:build"), ctx)

    assert replies


@pytest.mark.asyncio
async def test_the_router_always_acknowledges_the_tap_first(demo, replies, ctx):
    """An unacknowledged callback leaves a spinner on the user's button."""
    update = tap(replies, "menu:home")

    await handlers.on_callback(update, ctx)

    assert update.callback_query.answered is True


@pytest.mark.asyncio
async def test_adding_a_symbol_writes_it_to_the_watchlist(demo, replies, ctx, bot_db):
    from app.repositories import market as market_repo

    with bot_db() as db:
        market_repo.remove_from_watchlist(db, demo, "BTC")
        db.commit()

    await handlers.on_callback(tap(replies, "wl:add:BTC"), ctx)

    with bot_db() as db:
        assert "BTC" in {item.symbol for item in market_repo.list_watchlist(db, demo)}


@pytest.mark.asyncio
async def test_a_quiz_answer_is_marked(demo, replies, ctx):
    from app.services.education_engine import get_topic

    correct = get_topic("budgeting")["quiz"]["answer_idx"]

    await handlers.on_callback(tap(replies, f"quiz:budgeting:{correct}"), ctx)
    assert "Correct" in last(replies)

    await handlers.on_callback(tap(replies, f"quiz:budgeting:{(correct + 1) % 3}"), ctx)
    assert "Not quite" in last(replies)


# --- errors -------------------------------------------------------------

@pytest.mark.asyncio
async def test_the_error_handler_never_leaks_the_failure(replies, ctx, chat_stub):
    class FailedContext(FakeContext):
        error = ValueError("connection to finmentor:hunter2@db failed for user 41")

    await handlers.on_error(msg(replies), FailedContext())

    assert last(replies) == messages.SOMETHING_WENT_WRONG
    assert "hunter2" not in last(replies)


@pytest.mark.asyncio
async def test_the_error_handler_survives_a_chat_it_cannot_reply_to(ctx):
    class Dead:
        async def reply_text(self, *args, **kwargs):
            raise RuntimeError("chat not found")

    class DeadUpdate:
        effective_message = Dead()

    class FailedContext(FakeContext):
        error = ValueError("boom")

    await handlers.on_error(DeadUpdate(), FailedContext())     # must not raise


# --- a free-text what-if leads with the deterministic table --------------

@pytest.mark.asyncio
async def test_a_free_text_what_if_sends_the_table_before_the_prose(demo, replies, ctx):
    """The verified before/after must reach the user whatever the model says."""
    ctx.args = "what if I save 5m more each month".split()

    await handlers.simulate(msg(replies), ctx)

    table = next(r for r in replies if "CURRENT" in r)
    assert "SCENARIO" in table and "RESULT" in table
    assert replies.index(table) < replies.index(messages.THINKING)


@pytest.mark.asyncio
async def test_a_what_if_table_survives_a_dead_model(demo, replies, ctx):
    from app.ai.local_llm import FakeLocalProvider

    ctx.args = "what if I save 5m more each month".split()
    FakeLocalProvider.unavailable = True
    try:
        await handlers.simulate(msg(replies), ctx)
    finally:
        FakeLocalProvider.unavailable = False

    assert any("SCENARIO" in reply for reply in replies)


@pytest.mark.asyncio
async def test_a_question_that_is_not_a_what_if_skips_the_table(demo, replies, ctx):
    ctx.args = "what does diversification mean".split()

    await handlers.simulate(msg(replies), ctx)

    assert not any("SCENARIO" in reply for reply in replies)


@pytest.mark.asyncio
async def test_simulate_with_no_arguments_offers_the_menu(demo, replies, ctx):
    await handlers.simulate(msg(replies), ctx)

    assert messages.MENU_PROMPT in replies


@pytest.mark.asyncio
async def test_the_whatif_prompt_arms_the_next_message(demo, replies, ctx):
    await handlers.on_callback(tap(replies, "sim:whatif"), ctx)
    assert ctx.user_data[handlers.PENDING_KEY] == "whatif"

    await handlers.free_text(msg(replies, "what if I save 5m more each month"), ctx)

    assert any("SCENARIO" in reply for reply in replies)
