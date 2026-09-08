# FinMentor — Your Financial Twin

*Understand your money. Simulate your future.*

FinMentor is an AI-assisted personal financial-intelligence platform for
young adults (16–25). It is **not** a chatbot: the core is a deterministic
**Financial Twin** and a suite of engines (health score, what-if simulator,
time machine, decision simulator, market analytics). AI is used only to
explain results in plain English — never to compute them. The product is
English-only (see SPEC §31).

## Status

Phases 1-2 done. **Phase 1:** Postgres-backed foundation — full ORM models, the
initial Alembic migration, repositories, `POST/GET /api/users`, seeded demo user.
**Phase 2:** the deterministic engine — Financial Twin from the database,
Financial Health Score (5 x 20 points), Financial DNA bands, goal progress and
ETA, budget stability against a planned budget, and all 12 `/learn` topics, with
the profile / goals / health endpoints on top. No LLM is imported on any of
those paths.

Still typed stubs marked `# >>> finmentor-stub <<<` + `TODO(phase-N)`:
simulation (phase 3), the live market layer (phase 4), AI (phase 5), the
Telegram bot (phase 6).

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
python scripts/seed_demo_user.py   # demo user from SPEC section 29

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
  api/        FastAPI routes
  bot/        Telegram: handlers, inline keyboards, user-facing messages, formatting
tests/        unit/ (engine, models, repos, config)  +  api/
scripts/      seed_demo_user, fetch_market_snapshots
migrations/   Alembic environment + versions
docs/         SPEC, ROADMAP, ARCHITECTURE, DATA_MODEL
```

The legacy flat prototype (`config.py`, `main.py`, `bot/`, `data/`,
`analysis/`, `ai/`, `finance/`, `education/`) is retained until each piece is
ported — see the ROADMAP port checklist.

## API

```
POST /api/users                       GET  /api/users/{id}
GET  /api/financial-profile/{id}      PUT  /api/financial-profile/{id}   -> Financial Twin
GET  /api/health/{id}                 -> Health Score (5 components x 20)
GET  /api/health/{id}/dna             -> Financial DNA bands
GET  /api/goals/{user_id}             POST /api/goals    PUT /api/goals/{goal_id}
```

Both financial-profile verbs return the rebuilt **Financial Twin**, and accept an
optional `?period=YYYY-MM` (defaults to the current month) selecting which
month's expense records to use. The DNA sits at its own path rather than behind a
flag on the score, so each endpoint keeps a single response shape. Everything
else in spec section 22 arrives in phases 3-5.

## Product principle

FinMentor does **not** answer *"what should I buy?"* It answers *"here is what
your situation looks like, here is what changed, here is what could happen
under different assumptions, here is what the data means."*
