"""Every key in .env.example must land on a Settings field with the right type."""
from pathlib import Path

import pytest
from dotenv import dotenv_values

from app.core.config import Settings, get_settings, settings

ENV_EXAMPLE = Path(__file__).resolve().parents[2] / ".env.example"


def example_env() -> dict[str, str]:
    return {k: v for k, v in dotenv_values(ENV_EXAMPLE).items() if v is not None}


def test_env_example_exists():
    assert ENV_EXAMPLE.is_file()
    assert example_env(), "the example env file parsed to nothing"


def test_every_example_key_maps_to_a_settings_field():
    fields = set(Settings.model_fields)
    unknown = {key for key in example_env() if key.lower() not in fields}
    assert unknown == set(), f".env.example keys with no Settings field: {sorted(unknown)}"


def test_settings_load_values_from_the_environment(monkeypatch):
    for key, value in example_env().items():
        monkeypatch.setenv(key, value)
    loaded = Settings(_env_file=None)

    assert loaded.demo_mode is True
    assert loaded.env == "dev"
    assert loaded.log_level == "INFO"
    assert loaded.database_url.startswith("postgresql+psycopg://")
    assert loaded.redis_url == "redis://localhost:6379/0"
    assert loaded.market_cache_ttl_seconds == 3600
    assert loaded.local_llm_provider == "ollama"
    assert loaded.ollama_host == "http://localhost:11434"
    assert loaded.remote_llm_enabled is False
    assert loaded.remote_llm_provider == "none"
    assert loaded.remote_llm_timeout_seconds == pytest.approx(8.0)


def test_overrides_are_typed(monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("MARKET_CACHE_TTL_SECONDS", "60")
    monkeypatch.setenv("REMOTE_LLM_TIMEOUT_SECONDS", "2.5")
    loaded = Settings(_env_file=None)

    assert loaded.demo_mode is False
    assert loaded.market_cache_ttl_seconds == 60
    assert loaded.remote_llm_timeout_seconds == pytest.approx(2.5)


def test_secrets_default_to_empty_not_placeholders():
    defaults = Settings(_env_file=None, _env_ignore_empty=False)
    assert defaults.telegram_bot_token == ""
    assert defaults.remote_llm_api_key == ""


def test_get_settings_is_cached():
    assert get_settings() is get_settings() is settings
