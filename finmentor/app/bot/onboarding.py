"""The onboarding conversation: income -> expenses -> position -> goal -> risk.

A PTB `ConversationHandler`. Answers accumulate in `context.user_data` and
nothing is written until the last step, so abandoning halfway leaves no
half-built profile behind.

Numbers are read with `ai.intent.parse_amount`, the same parser the free-text
questions use — "5m", "5 million" and "5,000,000" mean the same thing here as
they do in a what-if.
"""
from __future__ import annotations

import re
from datetime import date

from telegram import Update
from telegram.ext import (
    CallbackQueryHandler, CommandHandler, ContextTypes, ConversationHandler,
    MessageHandler, filters,
)

from app.ai.intent import parse_amount
from app.bot import keyboards, messages
from app.bot.context import resolve_user_id, session
from app.repositories import goals as goals_repo
from app.repositories import profiles as profiles_repo
from app.repositories import users as users_repo
from app.schemas.finance import ExpenseBreakdown, FinancialProfileIn, GoalIn

(
    INCOME, INCOME_TYPE, EXPENSES, SAVINGS, DEBT, DEBT_PAYMENT, EMERGENCY,
    GOAL_NAME, GOAL_TARGET, GOAL_CURRENT, GOAL_DEADLINE, GOAL_PRIORITY, RISK,
) = range(13)

#: Asked one at a time, in the order a person actually thinks about them.
EXPENSE_CATEGORIES = (
    "housing", "food", "transportation", "bills",
    "education", "entertainment", "shopping", "other",
)

#: Three educational questions, tallied into a risk band. This is a
#: conversation starter, not a suitability assessment — the wording says so.
RISK_QUESTIONS = (
    {
        "question": "Your savings drop 20% in a month. What feels right?",
        "options": ["Move it somewhere safer", "Leave it alone", "Put more in"],
    },
    {
        "question": "Which sentence sounds more like you?",
        "options": [
            "I'd rather keep what I have",
            "A bit of ups and downs is fine",
            "I'll take swings for a bigger result",
        ],
    },
    {
        "question": "When would you need this money?",
        "options": ["Within a year", "In a few years", "Not for a long time"],
    },
)
RISK_BANDS = ("conservative", "moderate", "aggressive")

DATA_KEY = "onboarding"


def _draft(ctx: ContextTypes.DEFAULT_TYPE) -> dict:
    return ctx.user_data.setdefault(DATA_KEY, {"expenses": {}, "risk": []})


#: `parse_amount` reads magnitudes, not signs — "-5000" comes back as 5000.
#: Onboarding is the one place a user can type a minus, so it is checked here.
_NEGATIVE = re.compile(r"-\s*\d")


def _amount(text: str) -> float | None:
    """The amount in the text, signed, or None if there isn't one.

    Callers reject negatives themselves so they can say *why* — "that can't be
    negative" is a better prompt than "I couldn't read a number".
    """
    text = text or ""
    if text.strip().lower() in {"skip", "none", "no"}:
        return 0.0
    value = parse_amount(text)
    if value is None:
        return None
    return -value if _NEGATIVE.search(text) else value


async def _ask_expense(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """Prompt for whichever category comes next, or move on when done."""
    draft = _draft(ctx)
    index = len(draft["expenses"])
    if index >= len(EXPENSE_CATEGORIES):
        await update.effective_message.reply_text(messages.ASK_SAVINGS)
        return SAVINGS

    await update.effective_message.reply_text(
        messages.ASK_EXPENSE.format(category=EXPENSE_CATEGORIES[index]),
        parse_mode="Markdown",
        reply_markup=keyboards.skip_keyboard(),
    )
    return EXPENSES


# --- entry --------------------------------------------------------------

async def start_onboarding(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data[DATA_KEY] = {"expenses": {}, "risk": []}
    if update.callback_query is not None:
        await update.callback_query.answer()
    await update.effective_message.reply_text(messages.ONBOARD_INTRO)
    await update.effective_message.reply_text(messages.ASK_INCOME)
    return INCOME


# --- income + expenses --------------------------------------------------

async def got_income(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    value = _amount(update.message.text)
    if value is None:
        await update.message.reply_text(messages.NOT_A_NUMBER)
        return INCOME
    if value <= 0:
        await update.message.reply_text(messages.NEGATIVE_NUMBER)
        return INCOME

    _draft(ctx)["monthly_income"] = value
    await update.message.reply_text(
        messages.ASK_INCOME_TYPE, reply_markup=keyboards.income_type_picker()
    )
    return INCOME_TYPE


async def got_income_type(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, _, income_type = keyboards.parse_cb(query.data)
    _draft(ctx)["income_type"] = income_type or "fixed"
    return await _ask_expense(update, ctx)


async def got_expense(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    draft = _draft(ctx)
    category = EXPENSE_CATEGORIES[len(draft["expenses"])]

    if update.callback_query is not None:          # the Skip button
        await update.callback_query.answer()
        draft["expenses"][category] = 0.0
        return await _ask_expense(update, ctx)

    value = _amount(update.message.text)
    if value is None:
        await update.message.reply_text(messages.NOT_A_NUMBER)
        return EXPENSES
    if value < 0:
        await update.message.reply_text(messages.NEGATIVE_NUMBER)
        return EXPENSES

    draft["expenses"][category] = value
    return await _ask_expense(update, ctx)


# --- position -----------------------------------------------------------

async def got_savings(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    value = _amount(update.message.text)
    if value is None:
        await update.message.reply_text(messages.NOT_A_NUMBER)
        return SAVINGS
    if value < 0:
        await update.message.reply_text(messages.NEGATIVE_NUMBER)
        return SAVINGS
    _draft(ctx)["current_savings"] = value
    await update.message.reply_text(messages.ASK_DEBT)
    return DEBT


async def got_debt(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    value = _amount(update.message.text)
    if value is None:
        await update.message.reply_text(messages.NOT_A_NUMBER)
        return DEBT
    if value < 0:
        await update.message.reply_text(messages.NEGATIVE_NUMBER)
        return DEBT
    _draft(ctx)["debt"] = value
    if value == 0:
        _draft(ctx)["monthly_debt_payment"] = 0.0
        await update.message.reply_text(messages.ASK_EMERGENCY)
        return EMERGENCY
    await update.message.reply_text(messages.ASK_DEBT_PAYMENT)
    return DEBT_PAYMENT


async def got_debt_payment(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    value = _amount(update.message.text)
    if value is None:
        await update.message.reply_text(messages.NOT_A_NUMBER)
        return DEBT_PAYMENT
    if value < 0:
        await update.message.reply_text(messages.NEGATIVE_NUMBER)
        return DEBT_PAYMENT
    _draft(ctx)["monthly_debt_payment"] = value
    await update.message.reply_text(messages.ASK_EMERGENCY)
    return EMERGENCY


async def got_emergency(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    value = _amount(update.message.text)
    if value is None:
        await update.message.reply_text(messages.NOT_A_NUMBER)
        return EMERGENCY
    if value < 0:
        await update.message.reply_text(messages.NEGATIVE_NUMBER)
        return EMERGENCY
    _draft(ctx)["emergency_fund"] = value
    await update.message.reply_text(
        messages.ASK_GOAL_NAME, reply_markup=keyboards.skip_keyboard()
    )
    return GOAL_NAME


# --- first goal ---------------------------------------------------------

async def got_goal_name(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    skipped = update.callback_query is not None
    if skipped:
        await update.callback_query.answer()
    else:
        skipped = (update.message.text or "").strip().lower() in {"skip", "none"}

    if skipped:
        if _draft(ctx).get("goal_only"):
            ctx.user_data.pop(DATA_KEY, None)
            await update.effective_message.reply_text(messages.CANCELLED)
            return ConversationHandler.END
        return await _start_risk(update, ctx)

    name = (update.message.text or "").strip()
    if not name:
        await update.message.reply_text(messages.EMPTY_NAME)
        return GOAL_NAME

    _draft(ctx)["goal_name"] = name[:120]
    await update.message.reply_text(
        messages.ASK_GOAL_TARGET.format(name=name[:120]), parse_mode="Markdown"
    )
    return GOAL_TARGET


async def got_goal_target(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    value = _amount(update.message.text)
    if value is None or value <= 0:
        await update.message.reply_text(messages.NOT_A_NUMBER)
        return GOAL_TARGET
    _draft(ctx)["goal_target"] = value
    await update.message.reply_text(messages.ASK_GOAL_CURRENT)
    return GOAL_CURRENT


async def got_goal_current(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    value = _amount(update.message.text)
    if value is None:
        await update.message.reply_text(messages.NOT_A_NUMBER)
        return GOAL_CURRENT
    if value < 0:
        await update.message.reply_text(messages.NEGATIVE_NUMBER)
        return GOAL_CURRENT
    _draft(ctx)["goal_current"] = min(value, _draft(ctx)["goal_target"])
    await update.message.reply_text(
        messages.ASK_GOAL_DEADLINE, reply_markup=keyboards.skip_keyboard()
    )
    return GOAL_DEADLINE


async def got_goal_deadline(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    if update.callback_query is None:
        text = (update.message.text or "").strip()
        if text.lower() not in {"skip", "none"}:
            try:
                _draft(ctx)["goal_deadline"] = date.fromisoformat(text)
            except ValueError:
                await update.message.reply_text(messages.BAD_DATE)
                return GOAL_DEADLINE
    else:
        await update.callback_query.answer()

    await update.effective_message.reply_text(
        messages.ASK_GOAL_PRIORITY, reply_markup=keyboards.goal_priority_picker()
    )
    return GOAL_PRIORITY


async def got_goal_priority(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, _, level = keyboards.parse_cb(query.data)
    draft = _draft(ctx)
    draft["goal_priority"] = int(level) if level and level.isdigit() else 3

    if draft.get("goal_only"):
        return await _finish_goal_only(update, ctx)
    return await _start_risk(update, ctx)


# --- risk ---------------------------------------------------------------

async def _ask_risk_question(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    index = len(_draft(ctx)["risk"])
    question = RISK_QUESTIONS[index]
    await update.effective_message.reply_text(
        f"{index + 1}/{len(RISK_QUESTIONS)}  {question['question']}",
        reply_markup=keyboards.risk_question_options(index, question["options"]),
    )
    return RISK


async def _start_risk(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    await update.effective_message.reply_text(messages.RISK_INTRO)
    return await _ask_risk_question(update, ctx)


def tally_risk(answers: list[int]) -> str:
    """Mean answer index -> band. Rule-based and inspectable, on purpose."""
    if not answers:
        return "moderate"
    average = sum(answers) / len(answers)
    return RISK_BANDS[min(len(RISK_BANDS) - 1, int(round(average)))]


async def got_risk_answer(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    _, _, choice = keyboards.parse_cb(query.data)
    draft = _draft(ctx)
    draft["risk"].append(int(choice) if choice and choice.isdigit() else 1)

    if len(draft["risk"]) < len(RISK_QUESTIONS):
        return await _ask_risk_question(update, ctx)
    return await finish(update, ctx)


# --- write it all down --------------------------------------------------

def persist(db, user_id: int, draft: dict):
    """Everything the conversation collected, in one transaction.

    Returns the created goal (or None). No arithmetic happens here — the twin
    and the score are recomputed from these rows by the engine afterwards.
    """
    user = users_repo.get(db, user_id)
    profile_in = FinancialProfileIn(
        monthly_income=draft.get("monthly_income", 0.0),
        income_type=draft.get("income_type", "fixed"),
        expenses=ExpenseBreakdown(**draft.get("expenses", {})),
        current_savings=draft.get("current_savings", 0.0),
        debt=draft.get("debt", 0.0),
        monthly_debt_payment=draft.get("monthly_debt_payment", 0.0),
        emergency_fund=draft.get("emergency_fund", 0.0),
        risk_profile=tally_risk(draft.get("risk", [])),
    )
    profiles_repo.upsert(db, user, profile_in)

    return persist_goal(db, user_id, draft)


def persist_goal(db, user_id: int, draft: dict):
    """The goal the conversation collected, or None if it was skipped."""
    if not draft.get("goal_name"):
        return None
    return goals_repo.create(db, user_id, GoalIn(
        name=draft["goal_name"],
        target_amount=draft["goal_target"],
        current_amount=draft.get("goal_current", 0.0),
        deadline=draft.get("goal_deadline"),
        priority=draft.get("goal_priority", 3),
    ))


async def finish(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    from app.bot import handlers          # circular at import time, fine at call time

    draft = _draft(ctx)
    with session() as db:
        user_id = resolve_user_id(db, ctx.user_data, update.effective_user.id)
        persist(db, user_id, draft)

    ctx.user_data.pop(DATA_KEY, None)
    await update.effective_message.reply_text(messages.ONBOARD_DONE)
    await handlers.send_health(update, ctx)
    return ConversationHandler.END


# --- adding a goal later ------------------------------------------------
#
# The same five questions, entered from the Goals menu instead of onboarding.
# Reusing the steps means one place to fix a prompt, and one place a goal can
# be created.

async def start_add_goal(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data[DATA_KEY] = {"expenses": {}, "risk": [], "goal_only": True}
    if update.callback_query is not None:
        await update.callback_query.answer()
    await update.effective_message.reply_text(messages.ASK_GOAL_NAME)
    return GOAL_NAME


async def _finish_goal_only(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    from app.bot.handlers import goal_added_reply

    draft = _draft(ctx)
    ctx.user_data.pop(DATA_KEY, None)
    await goal_added_reply(update, ctx, draft)
    return ConversationHandler.END


def build_add_goal_handler() -> ConversationHandler:
    text = filters.TEXT & ~filters.COMMAND
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add_goal, pattern=r"^goal:add$")],
        states={
            GOAL_NAME: [MessageHandler(text, got_goal_name)],
            GOAL_TARGET: [MessageHandler(text, got_goal_target)],
            GOAL_CURRENT: [MessageHandler(text, got_goal_current)],
            GOAL_DEADLINE: [
                MessageHandler(text, got_goal_deadline),
                CallbackQueryHandler(got_goal_deadline, pattern=r"^onboard:skip$"),
            ],
            GOAL_PRIORITY: [CallbackQueryHandler(
                got_goal_priority, pattern=r"^goal:priority:")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
    )


async def cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    ctx.user_data.pop(DATA_KEY, None)
    await update.effective_message.reply_text(messages.CANCELLED)
    return ConversationHandler.END


def build_handler() -> ConversationHandler:
    text = filters.TEXT & ~filters.COMMAND
    return ConversationHandler(
        entry_points=[
            CommandHandler("onboard", start_onboarding),
            CallbackQueryHandler(start_onboarding, pattern=r"^onboard:start$"),
        ],
        states={
            INCOME: [MessageHandler(text, got_income)],
            INCOME_TYPE: [CallbackQueryHandler(
                got_income_type, pattern=r"^onboard:income_type:")],
            EXPENSES: [
                MessageHandler(text, got_expense),
                CallbackQueryHandler(got_expense, pattern=r"^onboard:skip$"),
            ],
            SAVINGS: [MessageHandler(text, got_savings)],
            DEBT: [MessageHandler(text, got_debt)],
            DEBT_PAYMENT: [MessageHandler(text, got_debt_payment)],
            EMERGENCY: [MessageHandler(text, got_emergency)],
            GOAL_NAME: [
                MessageHandler(text, got_goal_name),
                CallbackQueryHandler(got_goal_name, pattern=r"^onboard:skip$"),
            ],
            GOAL_TARGET: [MessageHandler(text, got_goal_target)],
            GOAL_CURRENT: [MessageHandler(text, got_goal_current)],
            GOAL_DEADLINE: [
                MessageHandler(text, got_goal_deadline),
                CallbackQueryHandler(got_goal_deadline, pattern=r"^onboard:skip$"),
            ],
            GOAL_PRIORITY: [CallbackQueryHandler(
                got_goal_priority, pattern=r"^goal:priority:")],
            RISK: [CallbackQueryHandler(got_risk_answer, pattern=r"^risk:")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
    )
