"""
Central configuration for the FinMentor hybrid AI financial assistant.

All secrets/keys are read from environment variables (see .env.example).
Nothing here should contain real credentials.
"""
import os
from dataclasses import dataclass, field
from typing import List


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


@dataclass
class Config:
    # --- Telegram ---
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")

    # --- Market data ---
    # Free tier works fine for a demo/prototype (5 requests/min, 500/day).
    # Get a free key at https://www.alphavantage.co/support/#api-key
    alpha_vantage_api_key: str = os.getenv("ALPHA_VANTAGE_API_KEY", "demo")
    # CoinGecko's public endpoints need no key for basic usage.
    coingecko_base_url: str = "https://api.coingecko.com/api/v3"

    # --- Local model (Ollama) ---
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

    # --- External API model (optional, used when reachable) ---
    api_model_provider: str = os.getenv("API_MODEL_PROVIDER", "none")  # "openai" | "anthropic" | "none"
    api_model_key: str = os.getenv("API_MODEL_KEY", "")
    api_model_name: str = os.getenv("API_MODEL_NAME", "gpt-4o-mini")
    api_timeout_seconds: float = _env_float("API_TIMEOUT_SECONDS", 8.0)

    # --- Watchlist used for the daily "hot assets" scan ---
    stock_watchlist: List[str] = field(default_factory=lambda: ["AAPL", "MSFT", "TSLA", "NVDA"])
    crypto_watchlist: List[str] = field(default_factory=lambda: ["bitcoin", "ethereum", "solana"])

    # --- Budget planner default rule ---
    # 50% needs / 30% wants / 20% savings-investing, the classic starting rule.
    budget_split = {"needs": 0.5, "wants": 0.3, "savings": 0.2}


settings = Config()
