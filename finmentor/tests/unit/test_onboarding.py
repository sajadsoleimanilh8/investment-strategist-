"""The onboarding conversation, driven step by step.

Rather than mocking PTB's dispatcher, the state functions are called directly
with stub Update/Context objects. That keeps the test about the thing that can
actually break — the state machine and what it writes — instead of about the
library.

No Telegram network and no model: the stubs record replies in a list.
"""
from datetime import date

import pytest
from telegram.ext import ConversationHandler

from app.bot import onboarding
from app.bot.context import session
from app.models.finance import ExpenseRecord
from app.repositories import goals as goals_repo
from app.repositories import profiles as profiles_repo
from app.repositories import users as users_repo

TELEGRAM_ID = 910_001


class FakeMessage:
    def __init__(self, sink: list, text: str | None = None):
        self.text = text
        self._sink = sink

    async def reply_text(self, text, **kwargs):
        self._sink.append(text)
        return FakeMessage(self._sink)


class FakeQuery:
    def __init__(self, sink: list, data: str):
        self.data = data
        self.answered = False
        self._sink = sink

    async def answer(self, *args, **kwargs):
        self.answered = True

    async def edit_message_text(self, text, **kwargs):
        self._sink.append(text)


class FakeUser:
    def __init__(self, telegram_id: int):
        self.id = telegram_id


class FakeUpdate:
    """Either a text message or a button press — never both, like the real thing."""

    def __init__(self, sink: list, *, text: str | None = None, data: str | None = None,
                 telegram_id: int = TELEGRAM_ID):
        self.effective_user = FakeUser(telegram_id)
        self.callback_query = FakeQuery(sink, data) if data is not None else None
        self.message = FakeMessage(sink, text) if data is None else None
        self.effective_message = self.message or FakeMessage(sink)
        self.effective_chat = None


class FakeContext:
    def __init__(self):
        self.user_data = {}
        self.args = []


@pytest.fixture
def replies():
    return []


@pytest.fixture
def ctx():
    return FakeContext()


def text_update(replies, text):
    return FakeUpdate(replies, text=text)


def tap(replies, data):
    return FakeUpdate(replies, data=data)


# --- the happy path -----------------------------------------------------

async def walk_happy_path(replies, ctx, *, telegram_id=TELEGRAM_ID):
    """Income -> 8 categories -> position -> a goal -> three risk answers."""
    def msg(text):
        return FakeUpdate(replies, text=text, telegram_id=telegram_id)

    def press(data):
        return FakeUpdate(replies, data=data, telegram_id=telegram_id)

    state = await onboarding.start_onboarding(msg("/onboard"), ctx)
    assert state == onboarding.INCOME

    state = await onboarding.got_income(msg("30m"), ctx)
    assert state == onboarding.INCOME_TYPE

    state = await onboarding.got_income_type(press("onboard:income_type:mixed"), ctx)
    assert state == onboarding.EXPENSES

    for _ in onboarding.EXPENSE_CATEGORIES[:-1]:
        state = await onboarding.got_expense(msg("2m"), ctx)
    state = await onboarding.got_expense(msg("2m"), ctx)       # the last one
    assert state == onboarding.SAVINGS

    state = await onboarding.got_savings(msg("45m"), ctx)
    assert state == onboarding.DEBT
    state = await onboarding.got_debt(msg("12m"), ctx)
    assert state == onboarding.DEBT_PAYMENT
    state = await onboarding.got_debt_payment(msg("1.5m"), ctx)
    assert state == onboarding.EMERGENCY
    state = await onboarding.got_emergency(msg("30m"), ctx)
    assert state == onboarding.GOAL_NAME

    state = await onboarding.got_goal_name(msg("Laptop"), ctx)
    assert state == onboarding.GOAL_TARGET
    state = await onboarding.got_goal_target(msg("60m"), ctx)
    assert state == onboarding.GOAL_CURRENT
    state = await onboarding.got_goal_current(msg("20m"), ctx)
    assert state == onboarding.GOAL_DEADLINE
    state = await onboarding.got_goal_deadline(msg("2027-06-01"), ctx)
    assert state == onboarding.GOAL_PRIORITY
    state = await onboarding.got_goal_priority(press("goal:priority:1"), ctx)
    assert state == onboarding.RISK

    await onboarding.got_risk_answer(press("risk:0:2"), ctx)
    await onboarding.got_risk_answer(press("risk:1:2"), ctx)
    return await onboarding.got_risk_answer(press("risk:2:1"), ctx)


@pytest.mark.asyncio
async def test_a_full_happy_path_writes_a_profile_a_goal_and_a_risk_band(
    bot_db, replies, ctx, monkeypatch
):
    monkeypatch.setattr("app.repositories.profiles.current_period", lambda *a, **k: "2026-09")
    # the last step renders the health view, which needs no network but does
    # need a chat to reply into
    monkeypatch.setattr(
        "app.bot.handlers.send_health",
        _record("health view sent", replies),
    )

    state = await walk_happy_path(replies, ctx)
    assert state == ConversationHandler.END

    with bot_db() as db:
        user = users_repo.get_by_telegram_id(db, TELEGRAM_ID)
        profile = profiles_repo.get_by_user(db, user.id)

        assert profile.monthly_income == 30_000_000
        assert profile.income_type == "mixed"
        assert profile.current_savings == 45_000_000
        assert profile.debt == 12_000_000
        assert profile.monthly_debt_payment == 1_500_000
        assert profile.emergency_fund == 30_000_000
        assert user.risk_profile == "aggressive"       # answers 2, 2, 1 -> mean 1.67

        expenses = db.query(ExpenseRecord).filter_by(user_id=user.id, period="2026-09").all()
        assert len(expenses) == len(onboarding.EXPENSE_CATEGORIES)
        assert all(row.amount == 2_000_000 for row in expenses)

        goals = goals_repo.list_for_user(db, user.id)
        assert len(goals) == 1
        assert goals[0].name == "Laptop"
        assert goals[0].target_amount == 60_000_000
        assert goals[0].current_amount == 20_000_000
        assert goals[0].deadline == date(2027, 6, 1)
        assert goals[0].priority == 1


def _record(marker: str, sink: list):
    async def handler(update, ctx):
        sink.append(marker)
    return handler


@pytest.mark.asyncio
async def test_the_conversation_ends_by_showing_the_health_view(
    bot_db, replies, ctx, monkeypatch
):
    monkeypatch.setattr("app.repositories.profiles.current_period", lambda *a, **k: "2026-09")
    monkeypatch.setattr("app.bot.handlers.send_health", _record("HEALTH", replies))

    await walk_happy_path(replies, ctx)

    assert "HEALTH" in replies


# --- validation ---------------------------------------------------------

@pytest.mark.asyncio
async def test_a_negative_income_re_prompts_instead_of_saving_it(bot_db, replies, ctx):
    await onboarding.start_onboarding(text_update(replies, "/onboard"), ctx)

    state = await onboarding.got_income(text_update(replies, "-5000"), ctx)

    assert state == onboarding.INCOME
    assert onboarding.messages.NEGATIVE_NUMBER in replies
    assert "monthly_income" not in ctx.user_data[onboarding.DATA_KEY]


@pytest.mark.asyncio
async def test_a_zero_income_re_prompts(bot_db, replies, ctx):
    await onboarding.start_onboarding(text_update(replies, "/onboard"), ctx)
    state = await onboarding.got_income(text_update(replies, "0"), ctx)

    assert state == onboarding.INCOME


@pytest.mark.asyncio
async def test_unreadable_text_re_prompts_rather_than_crashing(bot_db, replies, ctx):
    await onboarding.start_onboarding(text_update(replies, "/onboard"), ctx)
    state = await onboarding.got_income(text_update(replies, "quite a lot honestly"), ctx)

    assert state == onboarding.INCOME
    assert onboarding.messages.NOT_A_NUMBER in replies


@pytest.mark.asyncio
async def test_a_bad_date_re_prompts_and_keeps_the_goal(bot_db, replies, ctx):
    ctx.user_data[onboarding.DATA_KEY] = {
        "expenses": {}, "risk": [], "goal_name": "Laptop", "goal_target": 60_000_000,
    }
    state = await onboarding.got_goal_deadline(text_update(replies, "next june"), ctx)

    assert state == onboarding.GOAL_DEADLINE
    assert onboarding.messages.BAD_DATE in replies
    assert ctx.user_data[onboarding.DATA_KEY]["goal_name"] == "Laptop"


@pytest.mark.asyncio
async def test_skipping_an_expense_records_zero(bot_db, replies, ctx):
    ctx.user_data[onboarding.DATA_KEY] = {"expenses": {}, "risk": []}

    await onboarding.got_expense(tap(replies, "onboard:skip"), ctx)

    assert ctx.user_data[onboarding.DATA_KEY]["expenses"]["housing"] == 0.0


@pytest.mark.asyncio
async def test_a_goal_saved_beyond_its_target_is_capped(bot_db, replies, ctx):
    ctx.user_data[onboarding.DATA_KEY] = {
        "expenses": {}, "risk": [], "goal_name": "Laptop", "goal_target": 60_000_000,
    }
    await onboarding.got_goal_current(text_update(replies, "90m"), ctx)

    assert ctx.user_data[onboarding.DATA_KEY]["goal_current"] == 60_000_000


# --- skipping the goal --------------------------------------------------

@pytest.mark.asyncio
async def test_skipping_the_goal_goes_straight_to_the_risk_questions(
    bot_db, replies, ctx
):
    ctx.user_data[onboarding.DATA_KEY] = {"expenses": {}, "risk": []}

    state = await onboarding.got_goal_name(text_update(replies, "skip"), ctx)

    assert state == onboarding.RISK
    assert onboarding.messages.RISK_INTRO in replies


@pytest.mark.asyncio
async def test_a_profile_without_a_goal_is_still_written(bot_db, replies, ctx, monkeypatch):
    monkeypatch.setattr("app.repositories.profiles.current_period", lambda *a, **k: "2026-09")
    monkeypatch.setattr("app.bot.handlers.send_health", _record("HEALTH", replies))
    ctx.user_data[onboarding.DATA_KEY] = {
        "expenses": {"housing": 1_000_000}, "risk": [1, 1, 1],
        "monthly_income": 10_000_000,
    }

    await onboarding.finish(FakeUpdate(replies, text=""), ctx)

    with bot_db() as db:
        user = users_repo.get_by_telegram_id(db, TELEGRAM_ID)
        assert profiles_repo.get_by_user(db, user.id) is not None
        assert goals_repo.list_for_user(db, user.id) == []


# --- nothing is written until the end -----------------------------------

@pytest.mark.asyncio
async def test_abandoning_halfway_leaves_no_profile_behind(bot_db, replies, ctx):
    await onboarding.start_onboarding(text_update(replies, "/onboard"), ctx)
    await onboarding.got_income(text_update(replies, "30m"), ctx)
    state = await onboarding.cancel(text_update(replies, "/cancel"), ctx)

    assert state == ConversationHandler.END
    assert onboarding.DATA_KEY not in ctx.user_data
    with bot_db() as db:
        assert users_repo.get_by_telegram_id(db, TELEGRAM_ID) is None


# --- the risk tally -----------------------------------------------------

@pytest.mark.parametrize(
    "answers,expected",
    [
        ([0, 0, 0], "conservative"),
        ([1, 1, 1], "moderate"),
        ([2, 2, 2], "aggressive"),
        ([0, 1, 2], "moderate"),
        ([2, 2, 1], "aggressive"),
        ([], "moderate"),                # never answered -> the middle band
    ],
)
def test_the_risk_tally_is_a_plain_average(answers, expected):
    assert onboarding.tally_risk(answers) == expected


def test_there_are_three_risk_questions_each_with_three_options():
    assert len(onboarding.RISK_QUESTIONS) == 3
    assert all(len(q["options"]) == 3 for q in onboarding.RISK_QUESTIONS)


def test_every_expense_category_is_a_real_breakdown_field():
    from app.schemas.finance import ExpenseBreakdown

    assert set(onboarding.EXPENSE_CATEGORIES) == set(ExpenseBreakdown.model_fields)


# --- adding a goal later reuses the same steps --------------------------

@pytest.mark.asyncio
async def test_adding_a_goal_later_writes_only_a_goal(bot_db, replies, ctx, monkeypatch):
    monkeypatch.setattr("app.repositories.profiles.current_period", lambda *a, **k: "2026-09")
    monkeypatch.setattr("app.bot.handlers.send_health", _record("HEALTH", replies))
    await walk_happy_path(replies, ctx)

    recorded = []

    async def fake_reply(update, context, draft):
        recorded.append(draft)

    monkeypatch.setattr("app.bot.handlers.goal_added_reply", fake_reply)

    state = await onboarding.start_add_goal(tap(replies, "goal:add"), ctx)
    assert state == onboarding.GOAL_NAME
    await onboarding.got_goal_name(text_update(replies, "Bike"), ctx)
    await onboarding.got_goal_target(text_update(replies, "15m"), ctx)
    await onboarding.got_goal_current(text_update(replies, "1m"), ctx)
    await onboarding.got_goal_deadline(tap(replies, "onboard:skip"), ctx)
    state = await onboarding.got_goal_priority(tap(replies, "goal:priority:2"), ctx)

    assert state == ConversationHandler.END
    assert recorded[0]["goal_name"] == "Bike"
    assert recorded[0]["goal_priority"] == 2


@pytest.mark.asyncio
async def test_skipping_the_name_when_adding_a_goal_just_cancels(bot_db, replies, ctx):
    await onboarding.start_add_goal(tap(replies, "goal:add"), ctx)

    state = await onboarding.got_goal_name(text_update(replies, "skip"), ctx)

    assert state == ConversationHandler.END
    assert onboarding.messages.CANCELLED in replies
