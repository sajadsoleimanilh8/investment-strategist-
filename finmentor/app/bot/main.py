"""Telegram entry point. Run: python -m app.bot.main"""
from __future__ import annotations

from telegram.ext import Application, CommandHandler

from app.bot import handlers
from app.core.config import settings
from app.core.logging import configure_logging


def build_app() -> Application:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set (see .env.example)")
    app = Application.builder().token(settings.telegram_bot_token).build()
    app.add_handler(CommandHandler("start", handlers.start))
    # TODO(phase-6): register the rest.
    return app


def main() -> None:
    configure_logging()
    app = build_app()
    print("FinMentor bot running. Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
