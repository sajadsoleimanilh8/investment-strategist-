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
    #: Where the public live-price WebSocket gets its prices (app.market.live):
    #:
    #:   live  real provider, real prices (the default)
    #:   mock  deterministic synthetic ticks, which every surface must label
    #:         as demo data
    #:   off   no poll loop; the landing page collapses to a static panel
    #:
    #: Off under pytest and in the e2e webServer: no external API on a path
    #: those suites depend on being deterministic.
    market_live_source: str = "live"

    # email ------------------------------------------------------------------
    #: console | smtp. Console logs the message instead of sending it, which
    #: is what keeps the reset flow completable with nothing reachable.
    mail_transport: str = "console"
    mail_from: str = "FinMentor <no-reply@finmentor.local>"
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    #: Where a reset link points. The API and the SPA are not always the same
    #: origin, and the link has to open the *page*, not the endpoint.
    web_base_url: str = "http://localhost:5173"
    #: Short on purpose: a reset link is a bearer credential sitting in an
    #: inbox, and an hour is long enough to read an email.
    password_reset_ttl_minutes: int = 60

    # third-party sign-in --------------------------------------------------
    #: Absent credentials mean the provider is absent from the sign-in page,
    #: not shown and broken. See app/oauth/registry.py.
    google_client_id: str = ""
    google_client_secret: str = ""
    github_client_id: str = ""
    github_client_secret: str = ""
    #: Apple's client id is the Services ID, not the app id, and its secret is
    #: a JWT signed from the .p8 key rather than a stored string.
    apple_client_id: str = ""
    apple_team_id: str = ""
    apple_key_id: str = ""
    #: The contents of the .p8, newlines and all. In an env var they usually
    #: arrive escaped, so the provider unescapes before signing.
    apple_private_key: str = ""
    #: Where providers send the browser back. Must match what is registered
    #: with each of them, exactly, including the scheme.
    oauth_redirect_base: str = "http://localhost:8000"

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
    #: ceiling on a model reply. The persona asks for "concise by default,
    #: more when the topic needs it" rather than a fixed length, so this is a
    #: runaway guard, not the normal-case target — high enough to let a real
    #: deeper answer finish, low enough that a rambling one still gets cut off
    #: rather than reaching 400+ tokens.
    ai_max_tokens: int = 300
    #: how many past turns the free-chat path may see. Only the chat path has
    #: history at all — the precise paths (health, what-if, decision, market,
    #: education) stay stateless so the same question always gets the same
    #: answer from the same figures.
    ai_chat_history_turns: int = 6

    # remote LLM (optional)
    remote_llm_enabled: bool = False
    remote_llm_provider: str = "none"   # openai | anthropic | none
    remote_llm_model: str = "gpt-4o-mini"
    remote_llm_api_key: str = ""
    remote_llm_timeout_seconds: float = 8.0

    # web auth. `jwt_secret` has a development default so the test suite and a
    # local run need no setup; `test_a_production_run_refuses_the_dev_secret`
    # asserts that shipping it is impossible.
    jwt_secret: str = "dev-only-not-a-secret-please-replace-me"
    access_token_ttl_minutes: int = 30
    refresh_token_ttl_days: int = 14
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )
    #: per-IP on signup/login, per-user on /ai/ask. 0 disables the limiter.
    auth_rate_limit_per_minute: int = 10
    ask_rate_limit_per_minute: int = 20

    # budget engine default guideline (NOT presented as universally correct)
    budget_split: dict[str, float] = Field(
        default_factory=lambda: {"needs": 0.5, "wants": 0.3, "savings": 0.2}
    )


    @property
    def effective_market_live_source(self) -> str:
        """`market_live_source`, with DEMO_MODE's offline guarantee applied.

        DEMO_MODE means the whole product runs with nothing external
        reachable, so it can never resolve to `live`: the poll would fail
        forever and the landing page would sit on "Reconnecting" for the
        length of the demo, which is the definition of looking broken. It
        resolves to `off` rather than to `mock` because the section it feeds
        is headlined "real prices, not a mockup" — a demo that wants a moving
        ticker asks for `mock` explicitly, and gets a panel labelled as such.
        """
        if self.demo_mode and self.market_live_source == "live":
            return "off"
        return self.market_live_source

    @property
    def jwt_secret_is_default(self) -> bool:
        return self.jwt_secret == "dev-only-not-a-secret-please-replace-me"

    def check_production(self) -> None:
        """Refuse to start on a configuration that is only safe for a demo.

        A method rather than a few lines inside `get_settings` so it can be
        tested directly, against a constructed Settings, without a subprocess
        and a set of environment variables.
        """
        if self.demo_mode:
            return
        if self.jwt_secret_is_default:
            raise RuntimeError(
                "JWT_SECRET is still the development default. Generate one "
                "with `python -c \"import secrets; print(secrets.token_hex(32))\"` "
                "and put it in .env before running outside DEMO_MODE."
            )
        if self.mail_transport == "console":
            raise RuntimeError(
                "MAIL_TRANSPORT is 'console', which writes password-reset "
                "links to the log instead of sending them. A reset link is a "
                "bearer credential; in a log it is one anybody with log access "
                "can use. Set MAIL_TRANSPORT=smtp and the SMTP_* settings "
                "before running outside DEMO_MODE."
            )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.check_production()
    return settings


settings = get_settings()
