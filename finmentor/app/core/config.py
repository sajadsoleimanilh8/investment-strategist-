"""Central configuration. All secrets come from the environment / .env.

Supersedes the legacy top-level ``config.py`` (kept until the bot is ported).
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # runtime
    demo_mode: bool = True
    env: str = "dev"
    log_level: str = "INFO"

    # background jobs (off under pytest; see tests/conftest.py)
    enable_scheduler: bool = True

    # presentation
    currency_symbol: str = "$"

    # database / cache
    database_url: str = "postgresql+psycopg://finmentor:finmentor@localhost:5432/finmentor"
    redis_url: str = "redis://localhost:6379/0"

    # telegram
    telegram_bot_token: str = ""

    # market data
    alpha_vantage_api_key: str = "demo"
    coingecko_base_url: str = "https://api.coingecko.com/api/v3"
    market_cache_ttl_seconds: int = 3600
    stock_watchlist: list[str] = Field(default_factory=lambda: ["AAPL", "MSFT", "TSLA", "NVDA"])
    crypto_watchlist: list[str] = Field(default_factory=lambda: ["bitcoin", "ethereum", "solana"])

    # local LLM (default engine; "fake" is the deterministic test double)
    local_llm_provider: str = "ollama"
    local_llm_model: str = "llama3.2:3b"
    ollama_host: str = "http://localhost:11434"
    local_llm_temperature: float = 0.3   # low: the model explains, it does not invent
    ai_max_tokens: int = 400

    # remote LLM (optional)
    remote_llm_enabled: bool = False
    remote_llm_provider: str = "none"   # openai | anthropic | none
    remote_llm_model: str = "gpt-4o-mini"
    remote_llm_api_key: str = ""
    remote_llm_timeout_seconds: float = 8.0

    # budget engine default guideline (NOT presented as universally correct)
    budget_split: dict[str, float] = Field(
        default_factory=lambda: {"needs": 0.5, "wants": 0.3, "savings": 0.2}
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
