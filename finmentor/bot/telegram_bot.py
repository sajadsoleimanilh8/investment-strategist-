"""Wires the handlers up to a python-telegram-bot Application."""
from telegram.ext import Application, CommandHandler

from bot import handlers
from config import settings


def build_app() -> Application:
    if not settings.telegram_bot_token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not set. Copy .env.example to .env and fill it in "
            "(get a token from @BotFather on Telegram)."
        )

    app = Application.builder().token(settings.telegram_bot_token).build()

    app.add_handler(CommandHandler("start", handlers.start))
    app.add_handler(CommandHandler("watchlist", handlers.watchlist))
    app.add_handler(CommandHandler("ask", handlers.ask))
    app.add_handler(CommandHandler("learn", handlers.learn))
    app.add_handler(CommandHandler("budget", handlers.budget))

    return app


def run() -> None:
    app = build_app()
    print("FinMentor bot is running. Press Ctrl+C to stop.")
    app.run_polling()
