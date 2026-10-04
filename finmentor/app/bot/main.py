"""Telegram entry point. Run: python -m app.bot.main

Registration order matters. PTB dispatches to the first group that handles an
update, so the conversations go first — a message that is an answer to
"how much do you earn?" must not be read as a question for the AI.
"""
from __future__ import annotations

import logging
import time

from telegram import BotCommand
from telegram.error import NetworkError, TimedOut
from telegram.ext import (
    Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters,
)

from app.bot import handlers, messages, onboarding
from app.core.config import settings
from app.core.logging import configure_logging

log = logging.getLogger("finmentor.bot")

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
    ("link", handlers.link),
)


async def register_commands(app: Application) -> None:
    """Tell Telegram what this bot answers, so typing "/" shows a menu.

    Nothing did this, so the bot had twelve commands and advertised none: a
    user had to already know `/health` existed to find it. The descriptions
    come from `messages.COMMAND_HELP`, the same table `/help` renders, so the
    menu and the help text cannot disagree.

    Failure here is logged and swallowed. A bot that will not start because
    Telegram was slow to accept a cosmetic list is worse than a bot with no
    menu, and the next start tries again.
    """
    try:
        await app.bot.set_my_commands([
            BotCommand(name, description)
            for name, description in messages.COMMAND_HELP
        ])
        log.info("registered %d commands with telegram", len(messages.COMMAND_HELP))
    except Exception as exc:  # noqa: BLE001 - cosmetic, never fatal
        log.warning("could not register the command menu: %s", exc)


def build_app() -> Application:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set (see .env.example)")

    timeout = settings.telegram_timeout_seconds
    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .connect_timeout(timeout)
        .read_timeout(timeout)
        .write_timeout(timeout)
        .pool_timeout(timeout)
        .get_updates_connect_timeout(timeout)
        .get_updates_read_timeout(timeout)
        .post_init(register_commands)
        .build()
    )

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
    """Start polling, retrying startup when Telegram is briefly unreachable.

    Only startup is retried here. `run_polling` fails fast if `getMe` times
    out during initialisation, and on a flaky link that was the whole story:
    the process exited before it had served anyone. Once it is polling, PTB
    backs off and retries network errors itself.
    """
    configure_logging()
    attempts = max(1, settings.telegram_startup_attempts)
    for attempt in range(1, attempts + 1):
        app = build_app()
        try:
            log.info("starting the bot (attempt %d of %d)", attempt, attempts)
            app.run_polling()
            return
        except (TimedOut, NetworkError) as exc:
            if attempt == attempts:
                log.error("could not reach Telegram after %d attempts: %s",
                          attempts, exc)
                raise
            wait = min(60, 5 * attempt)
            log.warning("Telegram unreachable at startup (%s); retrying in %ds",
                        exc, wait)
            time.sleep(wait)


if __name__ == "__main__":
    main()
