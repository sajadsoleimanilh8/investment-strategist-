"""Entry point. Loads .env, then starts the Telegram bot."""
from dotenv import load_dotenv

load_dotenv()

from bot.telegram_bot import run  # noqa: E402  (must load .env first)

if __name__ == "__main__":
    run()
