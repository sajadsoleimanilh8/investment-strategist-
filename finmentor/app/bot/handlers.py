"""Thin Telegram handlers — all logic stays in app/services + app/ai.
# >>> finmentor-stub <<<
"""
from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from app.bot import messages
from app.bot.keyboards import main_menu


async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(messages.WELCOME, reply_markup=main_menu())


# TODO(phase-6): onboarding conversation, /profile /health /budget /goals
#   /simulate /market /watchlist /learn /ask /help, callback-query router.
