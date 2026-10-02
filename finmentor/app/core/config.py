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
    #: `text` or `json`. See `app.core.logging.LOG_FORMATS`.
    log_format: str = "text"

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
    #: Minutes a Telegram link code stays usable. Much shorter than a reset
    #: link, because a reset arrives in an inbox the user comes back to and
    #: this is read off a screen they are looking at right now. Ten minutes
    #: covers "open Telegram, find the bot, paste" without leaving a live
    #: grant on a laptop somebody else will sit down at.
    telegram_link_ttl_minutes: int = 10
    #: Redemption attempts per minute, per Telegram account. The code is 59
    #: bits, so this is not what makes guessing hopeless; it is what stops a
    #: single account hammering the endpoint from being free.
    telegram_link_attempts_per_minute: int = 5

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
    #: The bot's @name, without the @. Only used to build the deep link that
    #: saves a user typing the code. There is no way to derive it from the
    #: token without calling Telegram, which is a network call the API has no
    #: other reason to make, so an unset value means the link-code response
    #: carries the code and no deep link rather than a broken one.
    telegram_bot_username: str = ""

    # market data
    alpha_vantage_api_key: str = "demo"
    coingecko_base_url: str = "https://api.coingecko.com/api/v3"
    market_cache_ttl_seconds: int = 3600
    #: How much of the TTL may elapse before the refresh job runs.
    #:
    #: The job used to be scheduled at exactly `market_cache_ttl_seconds`,
    #: which is the one interval guaranteed to leave a gap: a snapshot goes
    #: stale at the same moment the run that would replace it is due, so every
    #: cycle had a window where requests fell through to a provider. Refreshing
    #: at half the TTL means the cache is replaced while it is still valid.
    market_refresh_fraction: float = 0.5
    #: Whether this process may run the scheduled jobs.
    #:
    #: `ENABLE_SCHEDULER` is per process, so two replicas with it on means two
    #: copies of every job and twice the provider traffic. When Redis is
    #: reachable the replicas take a short lease and only the holder runs, so
    #: leaving this on everywhere is safe. Without Redis it falls back to
    #: "whoever has it on", which is correct for the single-replica case this
    #: project actually deploys.
    scheduler_lease_seconds: int = 300

    # retention -------------------------------------------------------------
    #: `market_snapshots` is a cache and only its newest row per symbol is
    #: ever read. A few are kept so a deployment can see what it held.
    retention_market_snapshots_per_symbol: int = 5
    #: How long after expiry a spent reset row is kept. It exists so a second
    #: use of a link is refused rather than read as "no such token", which
    #: matters while the link might still be in an inbox and not after.
    retention_password_reset_days: int = 7
    #: The user's own saved runs, so this is a runaway guard rather than a
    #: retention policy: the list endpoint pages at 100 and a person runs a
    #: handful. The number is the owner's to change. 0 disables it.
    retention_simulations_per_user: int = 500
    #: How often the retention job runs. Daily: nothing here is urgent.
    retention_interval_seconds: int = 86_400
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
    #: Seconds to wait on one model generation.
    #:
    #: Was a flat 60. `/ai/ask` is a synchronous route, so it runs in
    #: Starlette's threadpool (40 workers by default), and a worker is held
    #: for the whole call. Forty slow generations therefore stalled every
    #: other route in the process, `/healthz` included — which fails the
    #: container healthcheck and restarts a container that was only busy.
    #: Twenty seconds is long enough for a 7B to finish a 300-token answer
    #: and short enough that a hung server costs a worker for a third of a
    #: minute rather than a full one.
    local_llm_timeout_seconds: float = 20.0
    #: How many model generations may be in flight at once.
    #:
    #: The real fix for the above: a ceiling that is independent of how many
    #: threadpool workers happen to exist. Past it, a request is refused
    #: quickly instead of queueing behind a model that is already saturated —
    #: Ollama serialises requests internally anyway, so the queue bought
    #: latency rather than throughput. 0 disables the ceiling.
    local_llm_max_concurrency: int = 4
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
    def market_refresh_interval_seconds(self) -> int:
        """How often to refresh the market cache.

        A fraction of the TTL, never the TTL itself. Scheduling the refresh at
        exactly the freshness window means a snapshot expires at the same
        moment its replacement is due, so there is always a gap in which
        requests fall through to a provider — which is the thing SPEC section
        24 says must not happen once warm.

        Floored at one second so a misconfigured fraction cannot produce a
        zero-interval job that spins.
        """
        return max(1, int(self.market_cache_ttl_seconds * self.market_refresh_fraction))

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
