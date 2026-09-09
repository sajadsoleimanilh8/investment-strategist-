"""Telegram handlers. A delivery layer and nothing more.

Every handler follows the same shape: open a session, resolve the user, ask
`app/services` (or `app/api/ask`) for the answer, render it with `views.py`,
reply. No handler computes a figure and no handler talks to a model directly.

Blocking work — the engine, the database, the LLM — runs in a worker thread via
`asyncio.to_thread`, so one slow 3B generation cannot stall the bot for every
other user.
"""
from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.error import BadRequest
from telegram.ext import ContextTypes

from app.ai import intent as intent_parser
from app.ai.intent import parse_amount
from app.api import ask as ask_pipeline
from app.api.deps import load_twin
from app.bot import keyboards, messages, views
from app.bot.context import is_onboarded, resolve_user_id, session
from app.core.logging import redact
from app.repositories import education as education_repo
from app.repositories import goals as goals_repo
from app.repositories import market as market_repo
from app.schemas.finance import GoalOut
from app.schemas.simulation import WhatIfParams
from app.services import market_engine
from app.market import cache as market_cache
from app.services.budget_engine import plan_budget
from app.services.decision_simulator import evaluate_purchase
from app.services.education_engine import get_topic, list_topics
from app.services.financial_dna import build_dna
from app.services.goal_engine import estimated_completion, progress_pct
from app.services.health_score import compute_health_score
from app.services.simulation_engine import run_what_if
from app.services.time_machine import compare_paths

log = logging.getLogger("finmentor.bot")

#: What the next free-text message means, when it means anything.
PENDING_KEY = "pending_input"
PARSE_MODE = "Markdown"


# --- plumbing -----------------------------------------------------------

async def _reply(update: Update, text: str, keyboard=None) -> None:
    await update.effective_message.reply_text(
        text, parse_mode=PARSE_MODE, reply_markup=keyboard,
        disable_web_page_preview=True,
    )


async def _edit(update: Update, text: str, keyboard=None) -> None:
    """Menus are edited in place; results are sent as new messages."""
    try:
        await update.callback_query.edit_message_text(
            text, parse_mode=PARSE_MODE, reply_markup=keyboard,
        )
    except BadRequest:                 # identical content, or too old to edit
        await _reply(update, text, keyboard)


async def _busy(update: Update, note: str = messages.CALCULATING) -> None:
    await update.effective_chat.send_action(ChatAction.TYPING)
    await update.effective_message.reply_text(note)


def _lookup_user(telegram_id: int, user_data: dict) -> int | None:
    """The onboarded user id, or None. Runs in a worker thread — it hits the DB."""
    with session() as db:
        user_id = resolve_user_id(db, user_data, telegram_id)
        return user_id if is_onboarded(db, user_id) else None


async def _needs_profile(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int | None:
    """Returns the user id, or None if they still have to onboard."""
    return await asyncio.to_thread(_lookup_user, update.effective_user.id, ctx.user_data)


def _goal_out(goal, monthly_savings: float) -> GoalOut:
    """A stored goal plus the two derived figures the engine owns."""
    goal_in = goals_repo.to_goal_in(goal)
    return GoalOut(
        **goal_in.model_dump(),
        id=goal.id,
        is_active=goal.is_active,
        progress_pct=progress_pct(goal_in),
        estimated_completion=estimated_completion(goal_in, monthly_savings),
    )


# --- blocking work (runs in a worker thread) ----------------------------

def _health_payload(user_id: int) -> str:
    with session() as db:
        twin = load_twin(db, user_id)
        return views.health_view(
            twin,
            compute_health_score(twin),
            build_dna(twin, completed_topics=education_repo.count_completed(db, user_id)),
        )


def _profile_payload(user_id: int) -> str:
    with session() as db:
        return views.profile_view(load_twin(db, user_id))


def _budget_payload(user_id: int) -> str:
    with session() as db:
        twin = load_twin(db, user_id)
    return views.budget_view(plan_budget(twin.income))


def _goals_payload(user_id: int) -> str:
    with session() as db:
        twin = load_twin(db, user_id)
        goals = goals_repo.list_for_user(db, user_id)
        return views.goals_view([_goal_out(goal, twin.monthly_savings) for goal in goals])


def _what_if_payload(user_id: int, params: WhatIfParams) -> str:
    with session() as db:
        twin = load_twin(db, user_id)
    return views.simulation_view(run_what_if(twin, params))


def _parse_simulation(question: str) -> WhatIfParams | None:
    """The scenario in the question, or None if it is not a what-if at all."""
    parsed = intent_parser.parse(question)
    return parsed.what_if if parsed.intent == "what_if" else None


def _purchase_payload(user_id: int, price: float) -> str:
    with session() as db:
        twin = load_twin(db, user_id)
    return views.decision_view(evaluate_purchase(twin, price))


def _time_machine_payload(user_id: int) -> str:
    with session() as db:
        twin = load_twin(db, user_id)
    return views.time_machine_view(compare_paths(twin))


def _market_payload(user_id: int) -> str:
    with session() as db:
        watched = market_repo.list_watchlist(db, user_id)
        reports = [
            market_engine.analyze(item.symbol, market_cache.get_or_fetch(db, item.symbol))
            for item in watched
        ]
    return views.market_view(market_engine.rank_by_momentum(reports))


def _watchlist_keyboard(user_id: int):
    with session() as db:
        symbols = [asset.symbol for asset in market_repo.list_active_assets(db)]
        watched = {item.symbol for item in market_repo.list_watchlist(db, user_id)}
    return symbols, watched


def _create_goal(user_id: int, draft: dict) -> str:
    """Write the goal the add-goal conversation collected, then render it."""
    from app.bot.onboarding import persist_goal

    with session() as db:
        goal = persist_goal(db, user_id, draft)
        twin = load_twin(db, user_id)
        return views.goal_added_view(_goal_out(goal, twin.monthly_savings))


def _ask_payload(user_id: int, question: str) -> str:
    with session() as db:
        return ask_pipeline.answer_question(db, user_id, question).text


# --- commands -----------------------------------------------------------

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = await _needs_profile(update, ctx)
    if user_id is None:
        await _reply(update, messages.WELCOME)
        await _reply(update, messages.NOT_ONBOARDED, keyboards.onboarding_prompt())
        return
    await _reply(update, messages.WELCOME)
    await _reply(update, messages.MENU_PROMPT, keyboards.main_menu())


async def help_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _reply(update, views.help_view(), keyboards.main_menu())


async def _guarded(update: Update, ctx: ContextTypes.DEFAULT_TYPE, work, *args,
                   note: str | None = None, keyboard=None) -> None:
    """The shape every data command shares: profile check, spinner, thread, reply."""
    user_id = await _needs_profile(update, ctx)
    if user_id is None:
        await _reply(update, messages.NOT_ONBOARDED, keyboards.onboarding_prompt())
        return
    if note:
        await _busy(update, note)
    else:
        await update.effective_chat.send_action(ChatAction.TYPING)
    text = await asyncio.to_thread(work, user_id, *args)
    await _reply(update, text, keyboard)


async def send_health(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _guarded(update, ctx, _health_payload, keyboard=keyboards.main_menu())


async def profile(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _guarded(update, ctx, _profile_payload, keyboard=keyboards.redo_profile())


async def budget(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _guarded(update, ctx, _budget_payload, keyboard=keyboards.main_menu())


async def goals(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _guarded(update, ctx, _goals_payload, keyboard=keyboards.goals_menu())


async def simulate(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """With text after the command it runs straight away; without, it offers a menu."""
    question = " ".join(ctx.args) if ctx.args else ""
    if not question:
        await _reply(update, messages.MENU_PROMPT, keyboards.simulate_menu())
        return
    await _run_free_text_simulation(update, ctx, question)


async def market(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _guarded(update, ctx, _market_payload, keyboard=keyboards.main_menu())


async def watchlist(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = await _needs_profile(update, ctx)
    if user_id is None:
        await _reply(update, messages.NOT_ONBOARDED, keyboards.onboarding_prompt())
        return
    symbols, watched = await asyncio.to_thread(_watchlist_keyboard, user_id)
    await _reply(update, "📈 *Watchlist* — tap to add or remove:",
                 keyboards.market_menu(symbols, watched))


async def learn(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await _reply(update, views.topics_list_view(list_topics()), keyboards.learn_menu(0))


async def ask(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    question = " ".join(ctx.args) if ctx.args else ""
    if not question:
        ctx.user_data[PENDING_KEY] = "ask"
        await _reply(update, messages.ASK_PROMPT)
        return
    await _run_ask(update, ctx, question)


async def goal_added_reply(update: Update, ctx: ContextTypes.DEFAULT_TYPE, draft: dict) -> None:
    """Called by the add-goal conversation once it has all five answers."""
    await _guarded(update, ctx, _create_goal, draft, keyboard=keyboards.goals_menu())


# --- free text ----------------------------------------------------------

async def _run_ask(update: Update, ctx: ContextTypes.DEFAULT_TYPE, question: str) -> None:
    user_id = await _needs_profile(update, ctx)
    if user_id is None:
        await _reply(update, messages.NOT_ONBOARDED, keyboards.onboarding_prompt())
        return
    await _busy(update, messages.THINKING)
    text = await asyncio.to_thread(_ask_payload, user_id, question)
    await _reply(update, text, keyboards.main_menu())


async def _run_free_text_simulation(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE, question: str
) -> None:
    """A what-if in the user's own words: the table first, then the explanation.

    The parser reads the sentence, the engine runs it, and `simulation_view`
    renders the before/after — so the user sees the verified figures whatever
    the model does afterwards. The prose is a second message from the same
    `/ask` pipeline, safety-checked on the way out.
    """
    params = _parse_simulation(question)
    if params is None:
        await _run_ask(update, ctx, question)
        return

    await _guarded(update, ctx, _what_if_payload, params, note=messages.CALCULATING)
    await _run_ask(update, ctx, question)


async def _run_purchase(update: Update, ctx: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    price = parse_amount(text)
    if price is None or price <= 0:
        await _reply(update, messages.UNREADABLE_AMOUNT)
        return
    await _guarded(update, ctx, _purchase_payload, price,
                   note=messages.CALCULATING, keyboard=keyboards.simulate_menu())


async def free_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """A message with no command. What it means depends on what we last asked."""
    pending = ctx.user_data.pop(PENDING_KEY, None)
    text = update.message.text or ""

    if pending == "purchase":
        await _run_purchase(update, ctx, text)
        return
    if pending == "whatif":
        await _run_free_text_simulation(update, ctx, text)
        return
    # "ask", "whatif", and an unprompted message all mean the same thing: the
    # intent parser decides, and an unreadable question gets the capabilities
    # answer rather than a guess.
    await _run_ask(update, ctx, text)


# --- callback router ----------------------------------------------------

async def on_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    area, action, arg = keyboards.parse_cb(query.data)

    if area == "menu":
        await _menu_callback(update, ctx, action)
    elif area == "sim":
        await _sim_callback(update, ctx, action)
    elif area == "wl":
        await _watchlist_callback(update, ctx, action, arg)
    elif area == "learn":
        await _learn_callback(update, ctx, action, arg)
    elif area == "quiz":
        await _quiz_callback(update, ctx, action, arg)
    else:
        await _edit(update, messages.MENU_PROMPT, keyboards.main_menu())


async def _menu_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE, action: str) -> None:
    if action == "home":
        await _edit(update, messages.MENU_PROMPT, keyboards.main_menu())
    elif action == "health":
        await send_health(update, ctx)
    elif action == "finances":
        await profile(update, ctx)
    elif action == "goals":
        await goals(update, ctx)
    elif action == "simulate":
        await _edit(update, messages.MENU_PROMPT, keyboards.simulate_menu())
    elif action == "market":
        await market(update, ctx)
    elif action == "learn":
        await _edit(update, views.topics_list_view(list_topics()), keyboards.learn_menu(0))
    elif action == "ask":
        ctx.user_data[PENDING_KEY] = "ask"
        await _reply(update, messages.ASK_PROMPT)


async def _sim_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE, action: str) -> None:
    if action == "whatif":
        ctx.user_data[PENDING_KEY] = "whatif"
        await _reply(update, messages.WHATIF_PROMPT)
    elif action == "purchase":
        ctx.user_data[PENDING_KEY] = "purchase"
        await _reply(update, messages.PURCHASE_PROMPT)
    elif action == "timemachine":
        await _guarded(update, ctx, _time_machine_payload,
                       note=messages.CALCULATING, keyboard=keyboards.simulate_menu())


def _toggle_watchlist(user_id: int, action: str, symbol: str) -> tuple[list[str], set[str]]:
    with session() as db:
        if action == "add":
            market_repo.add_to_watchlist(db, user_id, symbol)
        else:
            market_repo.remove_from_watchlist(db, user_id, symbol)
    return _watchlist_keyboard(user_id)


async def _watchlist_callback(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE, action: str, symbol: str | None
) -> None:
    user_id = await _needs_profile(update, ctx)
    if user_id is None or not symbol:
        await _reply(update, messages.NOT_ONBOARDED, keyboards.onboarding_prompt())
        return
    symbols, watched = await asyncio.to_thread(_toggle_watchlist, user_id, action, symbol)
    await _edit(update, "📈 *Watchlist* — tap to add or remove:",
                keyboards.market_menu(symbols, watched))


async def _learn_callback(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE, action: str, arg: str | None
) -> None:
    if action == "page":
        page = int(arg) if arg and arg.isdigit() else 0
        await _edit(update, views.topics_list_view(list_topics()), keyboards.learn_menu(page))
        return

    topic = get_topic(arg) if arg else None
    if topic is None:
        await _edit(update, views.topics_list_view(list_topics()), keyboards.learn_menu(0))
        return

    if action == "topic":
        await _edit(update, views.topic_view(topic), keyboards.topic_menu(arg))
    elif action == "quiz":
        await _edit(update, views.quiz_view(topic), keyboards.quiz_options(arg, topic))


async def _quiz_callback(
    update: Update, ctx: ContextTypes.DEFAULT_TYPE, topic_key: str, choice: str | None
) -> None:
    topic = get_topic(topic_key)
    if topic is None:
        await _edit(update, views.topics_list_view(list_topics()), keyboards.learn_menu(0))
        return
    chosen = int(choice) if choice and choice.isdigit() else -1
    await _edit(update, views.quiz_result_view(topic, chosen), keyboards.topic_menu(topic_key))


# --- errors -------------------------------------------------------------

async def on_error(update: object, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the failure, redacted; tell the user something plain.

    A user never sees a traceback, an id, or a database message — that is both
    a security boundary and a courtesy.
    """
    log.error("bot handler failed: %s", redact(str(ctx.error)), exc_info=ctx.error)
    message = getattr(update, "effective_message", None)
    if message is not None:
        try:
            await message.reply_text(messages.SOMETHING_WENT_WRONG)
        except Exception:                       # the chat may be gone entirely
            log.warning("could not deliver the error message")
