# FinMentor — Your Financial Twin

*Understand your money. Simulate your future.*

FinMentor is an AI-assisted personal financial-intelligence platform for
young adults (16–25). It is **not** a chatbot: the core is a deterministic
**Financial Twin** and a suite of engines (health score, what-if simulator,
time machine, decision simulator, market analytics). AI is used only to
explain results in plain English — never to compute them. The product is
English-only (see SPEC §31).

## Status

Phases 1-5 done. **Phase 1:** Postgres-backed foundation — full ORM models, the
initial Alembic migration, repositories, `POST/GET /api/users`, seeded demo user.
**Phase 2:** the deterministic engine — Financial Twin from the database,
Financial Health Score (5 x 20 points), Financial DNA bands, goal progress and
ETA, budget stability against a planned budget, and all 12 `/learn` topics, with
the profile / goals / health endpoints on top. No LLM is imported on any of
those paths.

**Phase 3:** the simulation layer — what-if scenarios, the Financial Time
Machine, the decision simulator, and a rule-based intent parser that turns
free text into engine params (still regex and keywords, no LLM).

**Phase 4:** the live market layer — `MarketDataProvider` abstraction with
AlphaVantage / CoinGecko / Mock, a read-through cache into `market_snapshots`,
an APScheduler refresh job, watchlist CRUD, and the market endpoints. Works
fully offline in `DEMO_MODE`.

**Phase 5:** the AI explanation layer — `POST /api/ai/ask` parses intent,
assembles a deterministic context, and hands the model only that context and
the question; a three-tier fallback (hybrid → local → deterministic
passthrough) and a safety layer that drops buy/sell sentences and discards
any answer containing a number that does not trace back to the context. Local
model is stock `llama3.2:3b` via Ollama; `LOCAL_LLM_PROVIDER=fake` is the
offline test double.

**Phase 6:** the Telegram bot — an onboarding conversation, ten commands, and
one inline-keyboard router. It is a thin delivery layer: message bodies are
built by pure functions in `app/bot/views.py` from engine output, and `/ask`
calls the same `app/api/ask.py` pipeline the HTTP route does.

Remaining: polish, rate limiting and deployment (phase 7).

- Full spec: [`docs/SPEC.md`](docs/SPEC.md)
- Phase plan: [`docs/ROADMAP.md`](docs/ROADMAP.md)
- Architecture: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- Data model: [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md)

## Quickstart

```bash
python -m venv .venv && . .venv/Scripts/activate     # Windows
pip install -r requirements.txt
cp .env.example .env          # defaults run in DEMO_MODE with no external services

docker compose up -d          # Postgres + Redis (or point DATABASE_URL at your own)
alembic upgrade head          # create the schema
python scripts/seed_demo_user.py   # demo user (SPEC 29) + market assets + watchlist
python -m scripts.fetch_market_snapshots   # warm the market cache (optional)

pytest                        # engine + model + API tests (SQLite, no infra needed)
uvicorn app.main:app --reload # API at http://localhost:8000/docs
python -m app.bot.main        # Telegram bot (needs TELEGRAM_BOT_TOKEN)
```

Tests run against in-memory SQLite by default. To run the same suite against a
real Postgres — which also enables the migration tests — point them at one:

```bash
FINMENTOR_TEST_DATABASE_URL=postgresql+psycopg://finmentor:finmentor@localhost:5432/finmentor_test pytest
```

Optional local LLM: install [Ollama](https://ollama.com), then
`ollama pull llama3.2:3b`.

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
tests/        unit/ (engine, models, repos, config)  +  api/
scripts/      seed_demo_user, fetch_market_snapshots
migrations/   Alembic environment + versions
docs/         SPEC, ROADMAP, ARCHITECTURE, DATA_MODEL
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
```

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

## Product principle

FinMentor does **not** answer *"what should I buy?"* It answers *"here is what
your situation looks like, here is what changed, here is what could happen
under different assumptions, here is what the data means."*
