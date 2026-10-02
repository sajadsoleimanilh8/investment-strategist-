"""The bot side of account linking: `/link CODE` and the deep link.

The pipeline is tested in `tests/api/test_telegram_link.py`. These are about
the two ways a code reaches it and what the chat shows afterwards.
"""
from __future__ import annotations

import pytest

from app.bot import handlers, messages
from app.bot.context import USER_ID_KEY
from app.core import security
from app.repositories import telegram_links as links_repo
from app.repositories import users as users_repo
from tests.unit.test_onboarding import FakeContext, FakeUpdate

BOT_TELEGRAM_ID = 70_001


@pytest.fixture
def replies():
    return []


@pytest.fixture
def ctx():
    return FakeContext()


@pytest.fixture
def web_account(bot_db):
    """A web user with a live code, plus a bot row that has said /start.

    Returns `(user_id, code)`. Committed, because the handler opens its own
    session through the bot's factory and will not see an uncommitted row.
    """
    with bot_db() as db:
        user = users_repo.create_web_user(db, email="linker@finmentor.local",
                                          password_hash="x")
        db.flush()
        code, code_hash = security.new_link_code()
        links_repo.create(db, user_id=user.id, code_hash=code_hash)
        db.commit()
        return user.id, code


def update(replies, telegram_id=BOT_TELEGRAM_ID):
    return FakeUpdate(replies, text="", telegram_id=telegram_id)


@pytest.mark.asyncio
async def test_link_with_a_code_connects_the_account(bot_db, web_account, replies, ctx):
    user_id, code = web_account
    ctx.args = [code]

    await handlers.link(update(replies), ctx)

    assert messages.LINK_DONE in " ".join(str(r) for r in replies)
    with bot_db() as db:
        assert users_repo.get(db, user_id).telegram_id == BOT_TELEGRAM_ID


@pytest.mark.asyncio
async def test_link_with_no_code_explains_where_to_get_one(replies, ctx):
    ctx.args = []

    await handlers.link(update(replies), ctx)

    assert messages.LINK_HOW in " ".join(str(r) for r in replies)


@pytest.mark.asyncio
async def test_link_accepts_a_code_split_across_arguments(bot_db, web_account,
                                                          replies, ctx):
    """`/link ABCD EFGH JKMN` is what happens when autocorrect eats hyphens."""
    user_id, code = web_account
    ctx.args = security.normalise_link_code(code)[:4], \
        security.normalise_link_code(code)[4:8], \
        security.normalise_link_code(code)[8:]

    await handlers.link(update(replies), ctx)

    with bot_db() as db:
        assert users_repo.get(db, user_id).telegram_id == BOT_TELEGRAM_ID


@pytest.mark.asyncio
async def test_a_bad_code_is_refused_without_repeating_it(bot_db, replies, ctx):
    ctx.args = ["ZZZZ-ZZZZ-ZZZZ"]

    await handlers.link(update(replies), ctx)

    said = " ".join(str(r) for r in replies)
    assert "not valid" in said
    assert "ZZZZ" not in said


@pytest.mark.asyncio
async def test_the_deep_link_links_without_onboarding(bot_db, web_account,
                                                      replies, ctx):
    """A user who tapped "connect" on a web page is not asking to onboard.

    `start` normally offers onboarding to a user with no profile. With a link
    payload it must do the link instead, or the tap lands in a questionnaire.
    """
    user_id, code = web_account
    ctx.args = [f"link_{security.normalise_link_code(code)}"]

    await handlers.start(update(replies), ctx)

    said = " ".join(str(r) for r in replies)
    assert messages.LINK_DONE in said
    assert messages.NOT_ONBOARDED not in said
    with bot_db() as db:
        assert users_repo.get(db, user_id).telegram_id == BOT_TELEGRAM_ID


@pytest.mark.asyncio
async def test_a_plain_start_still_onboards(bot_db, replies, ctx):
    ctx.args = []

    await handlers.start(update(replies), ctx)

    said = " ".join(str(r) for r in replies)
    assert messages.WELCOME in said
    assert messages.LINK_DONE not in said


@pytest.mark.asyncio
async def test_linking_clears_the_cached_user_id(bot_db, web_account, replies, ctx):
    """The cached id belonged to the row the merge deleted.

    `resolve_user_id` would heal it on the next update, but a handler that
    reads `user_data` directly would be holding a dead foreign key until it
    did.
    """
    user_id, code = web_account
    with bot_db() as db:
        bot_row = users_repo.get_or_create(db, telegram_id=BOT_TELEGRAM_ID)
        stale = bot_row.id
        db.commit()
    ctx.user_data[USER_ID_KEY] = stale
    ctx.args = [code]

    await handlers.link(update(replies), ctx)

    assert USER_ID_KEY not in ctx.user_data
    with bot_db() as db:
        assert users_repo.get(db, stale) is None
        assert users_repo.get(db, user_id).telegram_id == BOT_TELEGRAM_ID


@pytest.mark.asyncio
async def test_the_reply_names_what_moved(bot_db, web_account, replies, ctx):
    from app.models.goal import FinancialGoal

    user_id, code = web_account
    with bot_db() as db:
        bot_row = users_repo.get_or_create(db, telegram_id=BOT_TELEGRAM_ID)
        db.add(FinancialGoal(user_id=bot_row.id, name="Bot goal",
                             target_amount=100.0, current_amount=0.0, priority=1))
        db.commit()
    ctx.args = [code]

    await handlers.link(update(replies), ctx)

    said = " ".join(str(r) for r in replies)
    assert "Brought over from this chat: 1 goal." in said


def test_the_link_command_is_registered():
    from app.bot import main

    assert "link" in [name for name, _ in main.COMMANDS]


def test_help_mentions_linking():
    from app.bot import views

    assert "/link" in views.help_view()
