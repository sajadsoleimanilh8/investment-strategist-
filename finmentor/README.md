# FinMentor — Your Financial Twin

*Understand your money. Simulate your future.*

FinMentor is an AI-assisted personal financial-intelligence platform for
young adults (16–25). It is **not** a chatbot: the core is a deterministic
**Financial Twin** and a suite of engines (health score, what-if simulator,
time machine, decision simulator, market analytics). AI is used only to
explain results in plain English — never to compute them. The product is
English-only (see SPEC §31).

## Status

**Complete — phases 0 through 8.** Two delivery surfaces over one deterministic
core, 1823 tests, and a stack that comes up with one command.

![The dashboard](docs/screenshots/dashboard.png)

| | |
|---|---|
| **Engine** | Financial Twin, health score (5 x 20), Financial DNA, goals, budget, 12 lessons. **100% statement and branch coverage.** No LLM on any of these paths. |
| **Simulation** | what-if, time machine, decision simulator, and a rule-based intent parser — regex and keywords, no model. |
| **Market** | Alpha Vantage / CoinGecko / Mock behind one interface, a read-through cache, a refresh job. Works fully offline. |
| **AI** | `POST /api/ai/ask` hands the model a finished context and nothing else. Three tiers (hybrid → local → deterministic) and a safety layer that discards any answer containing a number it cannot trace back. |
| **Telegram** | onboarding conversation, ten commands, one callback router. |
| **Web** | argon2 + JWT, every route guarded, Redis rate limiting, Vite + React, dark theme with WCAG-checked contrast. |
| **Deploy** | `docker compose up -d` → web, API, Postgres, Redis. Migrations run on boot. |

One thing is deliberately left open — the live-API checks in
[`docs/PRE_DEPLOY.md`](docs/PRE_DEPLOY.md), which need network this machine
does not have. The local model is `qwen2.5:7b` (switched from `llama3.2:3b`;
one env var, see [`docs/ROADMAP.md`](docs/ROADMAP.md) for why), and the
Postgres test suite now refuses to run against anything that isn't obviously
a test database.

- **Where it stands now: [`docs/PROJECT_STATE.md`](docs/PROJECT_STATE.md)**
  — what is active, decided, blocked, and learned. Read this first.
- Full spec: [`docs/SPEC.md`](docs/SPEC.md)
- Phase plan: [`docs/ROADMAP.md`](docs/ROADMAP.md)
- Architecture: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- Data model: [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md)

## Quickstart

### The whole thing, one command

```bash
docker compose up -d
```

Web on <http://localhost:5173>, API on <http://localhost:8000>, Postgres and
Redis behind them. From a clean checkout that is the entire setup — the schema
migrates and the demo data seeds on boot. No `.env`, no API key, no network
beyond pulling the base images.

Walk it with [`docs/DEMO.md`](docs/DEMO.md).

### Running it from your shell

Infrastructure in Docker, the app on your machine — the usual dev loop:

```bash
cp .env.example .env
pip install -r requirements.txt
docker compose up -d db redis
alembic upgrade head
python scripts/seed_demo_user.py && python scripts/seed_market_assets.py

uvicorn app.main:app --reload          # API      :8000
cd web && npm install && npm run dev   # web      :5173
python -m app.bot.main                 # Telegram (needs TELEGRAM_BOT_TOKEN)
```

A local model is optional. Install [Ollama](https://ollama.com) and
`ollama pull llama3.2:3b` for prose answers; without it the AI layer serves the
same figures as a rendered table, which is the designed behaviour rather than a
failure.

### Tests

```bash
pytest                                   # 1613 tests, SQLite, no infrastructure
FINMENTOR_TEST_DATABASE_URL=postgresql+psycopg://finmentor:finmentor@localhost:5432/finmentor_test pytest
pytest --cov --cov-fail-under=100        # the app/services floor

cd web && npm test                       # 149 unit tests
cd web && npm run test:e2e               # the browser flow (skips without a browser)

scripts/ci_demo.sh                       # the gate: both surfaces, nothing external reachable
```

> The Postgres suite **drops every table** in the database it points at. Use a
> separate `finmentor_test` database — pointing it at a running stack's
> database wipes that stack.

### Deploying

`docker-compose.yml` is a demo configuration. For production, override:

| variable | why |
|---|---|
| `JWT_SECRET` | `python -c "import secrets; print(secrets.token_hex(32))"`. The app refuses to start on the development default with `DEMO_MODE=false`. |
| `DEMO_MODE=false` | turns on the production guards and the real market providers |
| `POSTGRES_PASSWORD` | the compose default is `finmentor` |
| `CORS_ORIGINS` | the real web origin, never `*` |
| `SEED_DEMO_DATA=false` | it creates a known user with a known telegram id |
| `VITE_API_BASE_URL` | a **build** arg — Vite inlines it, so it cannot be changed on a running container |

Then work through [`docs/PRE_DEPLOY.md`](docs/PRE_DEPLOY.md), which covers what
CI cannot: the three live external APIs, HTTPS, and a restored backup.

## Layout

```
app/
  core/       config, logging, security
  db/         SQLAlchemy base + session
  models/     ORM entities  (docs/DATA_MODEL.md)
  repositories/ thin CRUD helpers over the models (users, profiles, goals)
  schemas/    Pydantic I/O contracts (English field names)
  services/   DETERMINISTIC engine — twin, health, DNA, budget, goals,
              simulation, time machine, decision, market analytics, education
  market/     MarketDataProvider abstraction + AlphaVantage/CoinGecko/Mock
  ai/         local + remote LLM, intent parser, synthesizer, safety, prompts
  api/        FastAPI routes + ask.py (the shared question pipeline) + deps.py
  bot/        Telegram: handlers, callback router, onboarding conversation,
              inline keyboards, pure view builders, copy, formatting
web/          the browser client (Vite + React + TypeScript) — see web/README.md
  src/api/    one typed module per resource, over a client that refreshes on 401
  src/auth/   token handling, the route guard
  src/pages/  11 pages; src/styles/ holds the theme tokens and the skin
  e2e/        the Playwright flow, and the screenshot generator
docker/       entrypoint: wait for the database, migrate, then serve
scripts/      seed_demo_user, fetch_market_snapshots, demo_check, ci_demo.sh
scripts/ft/   local-model evaluation harness + the QLoRA fine-tune pipeline
tests/        unit/ (engine, models, repos, config)  +  api/
migrations/   Alembic environment + versions
docs/         SPEC, ROADMAP, ARCHITECTURE, DATA_MODEL, DEMO, PRE_DEPLOY
Dockerfile    the API image; web/Dockerfile builds the client
```

The v0 flat prototype was removed once every piece had been ported into
`app/` and re-tested there — see the note at the end of
[`docs/ROADMAP.md`](docs/ROADMAP.md).

## API

```
POST /api/users                       GET  /api/users/{id}
GET  /api/financial-profile/{id}      PUT  /api/financial-profile/{id}   -> Financial Twin
GET  /api/health/{id}                 -> Health Score (5 components x 20)
GET  /api/health/{id}/dna             -> Financial DNA bands
GET  /api/goals/{user_id}             POST /api/goals    PUT /api/goals/{goal_id}
POST /api/simulations                 GET  /api/simulations/{user_id}
GET  /api/market/assets               GET  /api/market/assets/{symbol}
GET  /api/market/watchlist/{user_id}  POST /api/market/watchlist/{user_id}
                                      DELETE /api/market/watchlist/{user_id}/{symbol}
POST /api/ai/ask                      GET  /api/ai/transcript/{user_id}
POST /api/auth/signup                 POST /api/auth/login
POST /api/auth/refresh                POST /api/auth/logout   GET /api/auth/me
GET  /api/learn                       GET  /api/learn/{key}
POST /api/learn/{key}/quiz            GET  /api/me/summary
```

Everything except `/api/auth/{signup,login,refresh,logout}` and `/healthz`
requires a bearer token, and a route taking a `{user_id}` answers 403 for
anyone else's. The Telegram bot does not go through HTTP at all — it imports
the pipeline directly, which is why adding auth did not touch it.

`POST /api/simulations` takes `{user_id, kind, params}` where `kind` is
`what_if`, `time_machine`, or `decision`; the run and its result are persisted
to the `simulations` table and listed back newest-first with `limit`/`offset`.

Both financial-profile verbs return the rebuilt **Financial Twin**, and accept an
optional `?period=YYYY-MM` (defaults to the current month) selecting which
month's expense records to use. The DNA sits at its own path rather than behind a
flag on the score, so each endpoint keeps a single response shape.

## Market data

Providers are tried in order and always fall back to `MockMarketProvider`, so
the product never looks broken offline; in `DEMO_MODE` the mock is the only
provider and its series are seeded per symbol, making every number
reproducible. Requests read through `app/market/cache.py` into
`market_snapshots`, and an APScheduler job (`ENABLE_SCHEDULER`, disabled under
pytest) refreshes them on `MARKET_CACHE_TTL_SECONDS` — so once warm, no market
request touches an external API. Every market payload carries the
educational-use disclaimer from SPEC section 27.

## The AI layer

`POST /api/ai/ask` follows the one rule in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md):

```
question -> intent.parse -> structured params -> deterministic engine
         -> verified context -> LLM writes prose -> safety layer -> user
```

The model receives the question and a finished JSON context, and nothing else —
no database handle, no engine call. It never computes a figure, so an outage
costs you the prose, not the numbers:

| tier | when | source |
|---|---|---|
| hybrid | local + remote both answer, local merges them | `hybrid` |
| local | remote disabled or failed (the default) | `local` |
| deterministic | the local model is down | `deterministic` |

A message the parser *cannot* read — "i want to save for a car", "thanks,
what next?" — is not a failure. It goes to the guide instead, which gets a
snapshot of figures the engine already computed plus the last few turns of
conversation, and replies warmly. That is the only path with history: the
precise ones stay stateless so the same question always yields the same
answer.

Every answer passes through `app/ai/safety.py`, which drops buy/sell
instructions, adds exactly one disclaimer, and — if the model emits a number
that does not trace back to the context — discards the model's text entirely
and renders the verified figures instead. A hallucinated number cannot reach a
user. Local model: stock `llama3.2:3b` via Ollama; set `LOCAL_LLM_PROVIDER=fake`
for the deterministic offline double that the tests use.

## The Telegram bot

```
TELEGRAM_BOT_TOKEN=... python -m app.bot.main
```

Commands: `/start /help /profile /health /budget /goals /simulate /market
/watchlist /learn /ask`. `/start` puts a new user into the onboarding
conversation and a returning one back at the menu.

Only `/ask` and a free-text simulation reach a model (SPEC section 23);
`/health`, `/budget`, `/goals`, `/profile`, `/market` and `/learn` are
deterministic end to end, and a test asserts they never call the synthesizer.
With Ollama stopped, `/ask` degrades to the verified figures and everything
else is unaffected.

## The web app

```bash
cd web && npm install && npm run dev        # :5173
```

A second delivery surface over the same API — `app/services`, `app/ai`,
`app/market` are reused unchanged, and the Telegram bot keeps working
throughout. Vite + React + TypeScript, TanStack Query, React Router. No UI
library.

Auth is argon2 for passwords and JWT for sessions: a 30-minute access token
held **in memory only**, and a 14-day refresh token in `localStorage` that is
rotated on every use. A token in storage is readable by any injected script; a
token in a variable dies with the tab, which is the right trade for a
short-lived credential.

Every `/api/*` route except signup, login, refresh and `/healthz` requires a
token, and every `{user_id}` is checked against it — a cross-user read is a 403,
tested route by route.

The theme lives entirely in the token block at the top of
`web/src/styles/layout.css`. Colours, type, radius and shadow are declared
there and applied by a separate `SKIN` block; the structure below neither knows
nor cares. `contrast.test.ts` computes WCAG ratios from those tokens and fails
the build if one drops below AA — which is how a border at 1.27:1 was caught
before it shipped.

![Green and red deltas on the watchlist](docs/screenshots/deltas.png)

## Demo and deployment

- [`docs/DEMO.md`](docs/DEMO.md) — a runbook for both surfaces, roughly eight
  minutes, works with no internet
- [`docs/PRE_DEPLOY.md`](docs/PRE_DEPLOY.md) — what a human has to verify that
  CI cannot
- [`scripts/ft/README.md`](scripts/ft/README.md) — how the local model was
  chosen, including the fine-tune that was built, measured, and not shipped

## Product principle

FinMentor does **not** answer *"what should I buy?"* It answers *"here is what
your situation looks like, here is what changed, here is what could happen
under different assumptions, here is what the data means."*
