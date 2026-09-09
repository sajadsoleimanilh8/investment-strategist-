"""Telegram entry point. Run: python -m app.bot.main

Registration order matters. PTB dispatches to the first group that handles an
update, so the conversations go first — a message that is an answer to
"how much do you earn?" must not be read as a question for the AI.
"""
from __future__ import annotations

from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters,
)

from app.bot import handlers, onboarding
from app.core.config import settings
from app.core.logging import configure_logging

COMMANDS = (
    ("start", handlers.start),
    ("help", handlers.help_command),
    ("profile", handlers.profile),
    ("health", handlers.send_health),
    ("budget", handlers.budget),
    ("goals", handlers.goals),
    ("simulate", handlers.simulate),
    ("market", handlers.market),
    ("watchlist", handlers.watchlist),
    ("learn", handlers.learn),
    ("ask", handlers.ask),
)


def build_app() -> Application:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set (see .env.example)")

    app = Application.builder().token(settings.telegram_bot_token).build()

    # 1. conversations — they own the user's next message while they run
    app.add_handler(onboarding.build_handler())
    app.add_handler(onboarding.build_add_goal_handler())

    # 2. commands
    for name, handler in COMMANDS:
        app.add_handler(CommandHandler(name, handler))

    # 3. one router for every inline button
    app.add_handler(CallbackQueryHandler(handlers.on_callback))

    # 4. anything else the user types is a question
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.free_text))

    app.add_error_handler(handlers.on_error)
    return app


def main() -> None:
    configure_logging()
    app = build_app()
    print("FinMentor bot running. Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
