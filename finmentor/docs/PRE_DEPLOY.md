# Pre-deploy checklist

Everything here needs a human with network access and real credentials. None of
it can be verified from the machine FinMentor was built on, and none of it is
covered by `scripts/ci_demo.sh` — which deliberately runs with every external
service unreachable.

Work through it on a staging deployment before the first production one.

---

## 1. Secrets

- [ ] **Generate a real `JWT_SECRET`.**

      python -c "import secrets; print(secrets.token_hex(32))"

      It goes in `.env` or your platform's secret store — never in source,
      never in `docker-compose.yml`, never in an image. Rotating it signs
      every existing session out, which is the intended behaviour if one leaks.

- [ ] **Change the database password** from the compose default (`finmentor`).
- [ ] **Confirm the startup guard fires.** With `DEMO_MODE=false` and the
      development key still in place the API must refuse to start. This is
      verified in CI (`tests/api/test_security_posture.py`) but is worth seeing
      once on the real deployment, because it is the last thing between a
      misconfigured rollout and forgeable tokens.
- [ ] `git log -p -- .env` returns nothing. `.env` is gitignored; this confirms
      it was never committed before that was true.

## 2. The three external APIs

Each provider is implemented and unit-tested against recorded shapes. What is
**unverified** is whether the live responses still match those shapes — an
upstream field rename would pass every test here and fail in production.

- [ ] **Alpha Vantage.** Set `ALPHA_VANTAGE_API_KEY`, `DEMO_MODE=false`, then:

      python -c "from app.market.alpha_vantage import AlphaVantageProvider; \
                 print(AlphaVantageProvider().get_daily_series('AAPL', days=7))"

      Expect 7 `PricePoint`s with plausible closes and ISO dates. Watch for the
      free tier's 25-requests-per-day cap — it returns a *note*, not an error,
      and the parser must treat that as no data rather than as a price.

- [ ] **CoinGecko, the live ticker.** Separate from the series call below and
      newer, so it has never met the real API either. With `DEMO_MODE=false`
      and `MARKET_LIVE_SOURCE=live`:

      python -c "from app.market.coingecko import CoinGeckoProvider;                  print(CoinGeckoProvider().get_spot(['BTC','ETH','SOL']))"

      Expect three `Spot`s with plausible USD prices and a 24h change. This is
      `/simple/price`, and the landing page's whole claim rests on it: if the
      shape has moved, the hub raises and the panel says "reconnecting"
      forever rather than showing a wrong number, which is the intended
      failure but not a good landing page. Watch the free tier's rate limit —
      the hub polls every 20s but only while somebody is connected.

- [ ] **CoinGecko.** No key needed on the free tier:

      python -c "from app.market.coingecko import CoinGeckoProvider; \
                 print(CoinGeckoProvider().get_daily_series('bitcoin', days=7))"

      Confirm the symbol mapping: CoinGecko wants `bitcoin`, not `BTC`.

- [ ] **The fallback still works when they fail.** Set an invalid key and
      confirm the watchlist still renders from the mock provider rather than
      erroring. This is the behaviour `market_engine.get_series` promises and
      the one most likely to matter at 3am.

- [ ] **The remote LLM**, only if you enable it. With `REMOTE_LLM_ENABLED=true`
      and a paid key, confirm `POST /api/ai/ask` returns `source=hybrid`, then
      pull the key and confirm it degrades to `local` — and with Ollama also
      stopped, to `deterministic`. Both failure paths are unit-tested against a
      fake; neither has been run against a real provider.

## 3. The stack

- [ ] `docker compose up -d` on the target host; all four containers healthy.
- [ ] `alembic current` matches `alembic heads`.
- [ ] `CORS_ORIGINS` lists the real web origin. Not `*`, not localhost. This
      is load-bearing twice over: the live-price WebSocket checks `Origin`
      against the same list, because a WebSocket upgrade never passes through
      CORS at all. Get this wrong and either every visitor's ticker is refused,
      or any page on the internet can open sockets against the hub.
- [ ] **The WebSocket survives the proxy.** `wss://` through whatever
      terminates TLS, with upgrade headers forwarded. A reverse proxy that
      drops them leaves the landing page reconnecting on a loop with nothing
      in the API log to explain it.
- [ ] **`MARKET_LIVE_SOURCE` is `live` in production.** `off` is the DEMO_MODE
      resolution and `mock` is for recorded demos; the page labels a mock feed
      as demo data, which is correct and is not what a real deployment wants.
- [ ] **The market cache is warm.** `GET /api/market/public/{symbol}` is
      cache-only by design (an unauthenticated route that could reach a
      provider is a way for anyone to spend the free-tier budget), so with a
      cold cache the landing sparkline has nothing to draw until live ticks
      accumulate. `ENABLE_SCHEDULER=true`, or run
      `scripts/fetch_market_snapshots.py` once after deploy.
- [ ] HTTPS terminates in front of the API. Tokens are bearer credentials in a
      header; over plain HTTP they are readable by anything on the path.
- [ ] Redis is reachable. If it is not, rate limiting silently allows every
      request — by design, but you should know which mode you are in.
- [ ] `SEED_DEMO_DATA` is **false** outside a demo. It creates a known user
      with a known telegram id.

## 4. The bot

- [ ] A production `TELEGRAM_BOT_TOKEN` from @BotFather, separate from any
      development one — two processes polling the same token fight over updates.
- [ ] Walk the SPEC §36 flow once in a real client: `/start` → onboarding →
      health → a what-if → a purchase → `/market` → `/ask` → `/learn`.
- [ ] Stop Ollama and repeat `/ask`. The reply must still carry the real
      figures, labelled as the deterministic answer.

## 5. After the first deploy

- [ ] Trigger a 500 deliberately and confirm the response carries a request id
      and no detail, and that the id appears in the logs.
- [ ] Confirm no log line contains a password, token, DSN or raw financial
      figure. `redact()` and `scrub_text()` cover the paths we control;
      a new logging call is how one escapes.
- [ ] Take a database backup and **restore it somewhere**. An untested backup
      is a hope, not a backup.

---

## What is already proven, and does not belong here

Verified by `scripts/ci_demo.sh` on every run, with nothing external reachable:

- the full Definition-of-Done flow on both surfaces
- the AI layer degrading to deterministic with the model unreachable, still
  carrying the engine's real figures
- rate limiting on `/api/auth/*`, `/api/ai/ask` and `/api/simulations`
- the auth guard on every route, and 403 on cross-user access
- 100% statement and branch coverage on `app/services`
