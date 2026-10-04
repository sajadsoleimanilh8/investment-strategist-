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
    # `127.0.0.1`, not `localhost`: see the comment on `Settings.database_url`.
    # The literal address is deliberate, and a test that pinned `localhost`
    # would quietly invite it back.
    assert loaded.redis_url == "redis://127.0.0.1:6379/0"
    assert "localhost" not in loaded.database_url
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


# --- the local model is a name, not a list ------------------------------
#
# The Part-B gate chose stock `llama3.2:3b`, but a fine-tune (`finmentor-3b`)
# or a bigger stock model has to be one env var away. Nothing in the app may
# assume which one is loaded.

@pytest.mark.parametrize(
    "model",
    ["llama3.2:3b", "qwen2.5:7b", "finmentor-3b", "some/registry:tag-v2"],
)
def test_any_model_name_is_accepted(monkeypatch, model):
    monkeypatch.setenv("LOCAL_LLM_MODEL", model)
    get_settings.cache_clear()
    try:
        assert get_settings().local_llm_model == model
    finally:
        get_settings.cache_clear()


def test_no_model_name_is_hard_coded_outside_config():
    """A tag written into a module is a deployment that cannot be retargeted."""
    import pathlib

    app_dir = pathlib.Path(__file__).resolve().parents[2] / "app"
    def code_lines(path):
        """Comments may name a model as an example; code may not depend on one."""
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                yield line.split("  #")[0]

    offenders = [
        path.relative_to(app_dir).as_posix()
        for path in app_dir.rglob("*.py")
        if path.name != "config.py"
        and any(tag in line for line in code_lines(path)
                for tag in ("llama3.2:3b", "finmentor-3b"))
    ]
    assert offenders == [], f"model tag hard-coded in: {offenders}"


def test_the_provider_switch_still_reaches_the_offline_double():
    """`fake` must keep working whatever the model name says."""
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setenv("LOCAL_LLM_PROVIDER", "fake")
    monkeypatch.setenv("LOCAL_LLM_MODEL", "finmentor-3b")
    get_settings.cache_clear()
    try:
        from app.ai.local_llm import FakeLocalProvider, get_local_provider

        assert isinstance(get_local_provider(), FakeLocalProvider)
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_a_model_ollama_does_not_have_degrades_instead_of_crashing(monkeypatch):
    """`LOCAL_LLM_MODEL=finmentor-3b` on a machine that never built it must
    serve the verified figures, not a 500. Pointed at a closed port so the
    failure is a refused connection, which is what an absent Ollama looks
    like."""
    from app.ai import synthesizer
    from app.core.config import settings as live

    monkeypatch.setattr(live, "local_llm_provider", "ollama")
    monkeypatch.setattr(live, "local_llm_model", "finmentor-3b")
    monkeypatch.setattr(live, "ollama_host", "http://127.0.0.1:1")

    result = synthesizer.explain("why?", {"financial_health_score": 62.3})

    assert result["source"] == "deterministic"
    assert "62.3" in result["text"]
    assert result["safety_report"]
