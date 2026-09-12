# FinMentor — Phase Roadmap

Build order follows the architectural rule: deterministic engine first,
tests before AI, AI before Telegram. Each phase ends green (`pytest`) and
independently demoable. Check items off as you go.

Legend: `[ ]` todo · `[~]` partial/stub exists · `[x]` done
Stub markers in code: `# >>> finmentor-stub <<<` + `TODO(phase-N)`.

---

## Phase 0 — Skeleton  `[x]`
- [x] `app/` clean-architecture tree, docs, tooling (`pytest.ini`, requirements, docker-compose)
- [x] Port + test deterministic market analytics -> `app/services/market_engine.py`
- [x] Port + test budget engine -> `app/services/budget_engine.py`
- [x] Financial Twin maths implemented + tested
- [x] Typed stubs for every remaining module

## Phase 1 — Foundation  `[x]`
- [x] `app/core/config.py` verified against `.env.example` (all keys load)
- [x] `app/db/session.py` + `app/db/base.py` connect to Postgres (docker-compose up)
- [x] Finish all ORM models in `app/models/` (columns, FKs, relationships, indexes)
- [x] `alembic init migrations`; wire `env.py`; autogenerate + apply initial schema
- [x] Repositories / CRUD helpers for users, profiles, goals (`app/repositories/`)
- [x] `POST /api/users`, `GET /api/users/{id}` + tests
- [x] `scripts/seed_demo_user.py` writes the real demo user through repositories
- [x] Logging configured; secret redaction verified (`redact()` covers tokens,
      identifiers and raw figures; the API access log carries no bodies)
- **Done when:** `docker compose up`, `alembic upgrade head`, seed script, and
  `pytest` all succeed; user endpoints pass.

## Phase 2 — Financial Engine (no AI)  `[x]`
- [x] `financial_twin.build_twin` wired to DB profile + expenses + goals
      (assembled in `app/api/deps.py::load_twin`, keeping `app/services` free of DB)
- [x] `health_score.compute_health_score` — all 5 components; formulas finalised
      and documented in the module docstring
- [x] Planned-vs-actual spending: `financial_profiles.planned_budget_json` carried
      into the twin; `score_budget_stability` = per-category absolute miss vs plan
      (<=5% deviation -> 20 pts, >=50% -> 0, no plan -> neutral 12)
- [x] `score_goal_progress` (priority-weighted mean; priority 1 weighs 5x)
- [x] `financial_dna.build_dna` — bands off the component scores
      (Strong >=14/20, Moderate >=7/20) + knowledge level from completed
      `education_progress` topics (Intermediate at 4, Advanced at 9)
- [x] `goal_engine.estimated_completion` (calendar months; None past a 100-year horizon)
- [x] Expand `education_engine.TOPICS` to full 12 (explanation/example/mistake/quiz)
- [x] Endpoints: `GET/PUT /api/financial-profile/{id}`, `GET /api/health/{id}`,
      `GET /api/health/{id}/dna`, `GET/POST/PUT /api/goals`
- [x] Unit tests: savings rate, emergency fund, debt burden, budget stability,
      health score total, goal progress + ETA, DNA bands, all 12 topics
- **Done when:** demo user -> Health Score + DNA + goal progress, entirely
  deterministic, `< 500 ms`, no LLM import on these paths.
  *Verified: demo user scores 62.3/100 (20 / 6.1 / 17.5 / 12 / 6.7) with DNA
  Strong / Weak / Strong / Weak / Moderate / Beginner, served in ~10 ms.*

## Phase 3 — Simulation  `[x]`
- [x] `simulation_engine.apply_scenario` + `project` (straight-line); the twin's
      derived arithmetic lives once in `financial_twin.derive_figures`, shared by
      `build_twin` and `apply_scenario`
- [x] `simulation_engine.run_what_if` -> `SimulationOut` with deltas
- [x] `time_machine.compare_paths` over the 4 presets (stable order, one shared goal)
- [x] `decision_simulator.evaluate_purchase` (affordable = savings stay >= 0)
- [x] `ai/intent.parse` — English number/percent parsing ("5M", "5 million",
      "15%"), rule-first intent routing; `llm_fallback` is the phase-5 seam and
      currently returns an unparsed result rather than guessing
- [x] `POST /api/simulations`, `GET /api/simulations/{user_id}` (+ persist to
      `simulations`; no migration needed, the table already existed)
- [x] Unit tests: scenario maths, projection, time machine, decision sim, 21
      parser fixtures, architecture guards (no AI import on any simulator path)
- **Done when:** "what if I save $5M more each month?" -> parsed params ->
  numeric before/after + goal-date shift, no LLM doing arithmetic.
  *Verified live: parsed to `monthly_savings_delta=5,000,000`; savings
  10.5M -> 15.5M/mo, goal 68.3% -> 85.0% at a 2-month horizon, goal date
  2027-01-08 -> 2026-12-08.*

## Phase 4 — Market  `[x]`
- [x] `market/cache.py` read-through cache -> `market_snapshots`
      (snapshots are keyed by symbol, so a request for more days than were
      stored is a miss; Redis left as a documented phase-7 accelerator)
- [x] APScheduler job in `app/main.py` lifespan (gated by `ENABLE_SCHEDULER`,
      off under pytest); `scripts/fetch_market_snapshots.py` runs standalone
- [ ] Real `AlphaVantageProvider` / `CoinGeckoProvider` verified against live
      APIs — **not done**: needs live keys and network, so it stays open. The
      provider loop and its fallback to mock are covered by tests.
- [x] Watchlist CRUD + `market_assets` seed list (`scripts/seed_market_assets.py`)
- [x] Endpoints: `GET /api/market/assets`, `/api/market/assets/{symbol}`,
      `GET/POST /api/market/watchlist/{user_id}`,
      `DELETE /api/market/watchlist/{user_id}/{symbol}`
- [x] Disclaimer on every market payload (schema default, never overridden)
- [x] Tests: cache hit/miss/stale, provider fallback to mock, ranking, the
      scheduled job, and a warm-cache zero-provider-call guard
- **Done when:** `/market` works live AND with network off (mock), cache keeps
  external calls off the request path.
  *Verified in DEMO_MODE against Postgres: the demo watchlist ranks
  NVDA / BTC / AAPL / ETH by 7d momentum, and six repeat requests were served
  with zero provider fetches.*

## Phase 5 — AI  `[x]`
- [x] `ai/local_llm.py` verified against a running Ollama model
      (`/api/chat`, temperature 0.3; `available()` checks the model is actually
      installed, cached 30s. `FakeLocalProvider` is the offline test double —
      `LOCAL_LLM_PROVIDER=fake`, which is what pytest uses.)
- [x] `ai/remote_llm.py` returns None on any failure, so a dead remote silently
      degrades to local. **openai/anthropic not exercised against live APIs** —
      that needs paid keys; the disabled-by-default and failure paths are tested.
- [x] `ai/synthesizer.explain` — context-only prompting, hybrid merge, and a
      single exit point (`_finish`) so no answer can skip the safety layer
- [x] `ai/safety.enforce` — one disclaimer, buy/sell sentences dropped,
      ungrounded numbers downgraded to the rendered context
- [x] `POST /api/ai/ask` — parses intent, assembles the deterministic context,
      and persists the exchange to `chat_sessions`; the LLM computes nothing
- [x] Tests: remote-up -> hybrid, remote-down -> local, local-down ->
      deterministic passthrough; safety scrubbing; "data unavailable" path
- **Done when:** `/ask` explains a real health score / simulation with all three
  fallback tiers covered by tests.

## Phase 6 — Telegram  `[x]`
- [x] Onboarding conversation (income -> 8 expense categories -> position ->
      first goal -> 3 risk questions). Nothing is written until the last step,
      so an abandoned run leaves no half-built profile.
- [x] All commands + one inline-keyboard callback router. Every payload is
      `"<area>:<action>[:<arg>]"`, decoded in a single `parse_cb`.
- [x] English copy in `app/bot/messages.py`; every figure rendered through
      `formatting.py` (currency via `settings.currency_symbol`)
- [x] Each command wired to `app/services`; `/ask` and free-text simulations go
      through `app/api/ask.py`, the pipeline the HTTP route also uses. Blocking
      work runs in `asyncio.to_thread`; anything slow says "Calculating…" first.
- [x] Port/retire legacy `bot/`, `main.py`, top-level `config.py` — deleted on
      2026-09-08 once everything had been ported into `app/` (see the note below)
- [x] `app/bot/views.py` is pure (data in, string out, no Telegram import), so
      every message body is unit-tested against real engine output
- [x] **Warm conversational layer** — a message the parser cannot read no longer
      gets a canned list. It goes to `synthesizer.chat` with a pre-computed
      snapshot (`deps.build_chat_snapshot`) and the last
      `AI_CHAT_HISTORY_TURNS` exchanges, and comes back as prose that points at
      the right feature. The precise paths stay stateless and unchanged; the
      canned capabilities answer survives as the floor when the model is down.
- **Done when:** the full Definition-of-Done flow works from Telegram in DEMO_MODE.
  *Verified live on 2026-09-09 against a real bot token, Postgres and
  `llama3.2:3b`: the flow runs end to end in Telegram itself, not just
  in-process.*

## Local model — evaluation, and the fine-tune we did not do  `[x]`
- [x] 22-probe evaluation set built from **real** engine output for four
      synthetic people (`scripts/ft/make_probes.py`), graded on seven checks
      that each name a defect seen live (`scripts/ft/probes.py`)
- [x] Three defects fixed by changing what the model is *shown*, not by
      training: the chat snapshot carries the engine's verdict per component
      and no raw score; what-if / purchase contexts get a labelled
      `BEFORE … | AFTER …` block ahead of the JSON; `safety` grounds on
      magnitude so a negative figure no longer flags its own rendering
- [x] Gate run, 3 passes x 22 probes: **llama3.2:3b 20.0/22 (91%)**,
      qwen2.5:3b 19.3/22 (88%). `qwen2.5:7b` untested — `ollama pull` blocked
      from this machine twice (DNS, then a blocked socket).
- **Decision: no fine-tune.** A stock model clears the bar and the defects a
  fine-tune targeted are already gone. Fine-tuning is a retrain obligation on
  every base-model bump; taking that on for defects a better prompt payload
  removed would be paying rent on nothing. The path to do it later, and what it
  would plausibly buy, is written up in `scripts/ft/README.md`.
- [x] **The fine-tune was built anyway (2026-09-10) and lost.** QLoRA r=16 on
      584 generated pairs, 15.7 min / 4.8 GB on the 5070 Ti, eval loss 0.0497.
      Stock scored 21.0/22, `finmentor-3b` 17.7/22 — grounding and verdicts are
      fine, but it over-fit the composer's templates and collapsed the explain
      path into the chat shape. Pipeline committed and repeatable
      (`scripts/ft/`), weights not shipped. `LOCAL_LLM_MODEL` stays
      `llama3.2:3b`. Full write-up in `scripts/ft/README.md`.
- **`LOCAL_LLM_MODEL` stays a plain env var.** No model tag is hard-coded
  outside `config.py`, and a test asserts it.

## Phase 7 — Website  `[x]`

A second delivery surface over the **same** FastAPI backend. `app/services`,
`app/ai`, `app/market` and `app/api` are reused unchanged, and the Telegram bot
kept working throughout — it never called the API over HTTP, it imports
`app/api/ask.py` and `app/api/deps.py` directly, so guarding the routes could
not break it.

- [x] **Auth** — `app/core/security.py` is real: argon2id password hashing,
      HS256 JWTs with a checked `typ` (30-minute access, 14-day rotating
      refresh), and a bearer-header parser. Migration `0129e065904c` adds
      `email` + `password_hash`, makes `telegram_id` nullable, and adds a CHECK
      that every row carries at least one identity.
- [x] `POST /api/auth/{signup,login,refresh,logout}`, `GET /api/auth/me`,
      and a `require_user` dependency.
- [x] Every `/api/*` route except signup/login/refresh/logout and `/healthz` is
      guarded **at the router**, so a route added later is protected by default
      rather than by remembering. `{user_id}` paths resolve through
      `OwnedUserId` (403 on someone else's data); the three routes carrying a
      user id in the *body* call `assert_owns`. Both are tested case-by-case
      across all 22 routes.
- [x] CORS from `settings.cors_origins`; Redis rate limiting on signup/login
      (per IP) and `/api/ai/ask` (per user), which logs and allows the request
      if Redis is unreachable — a cache outage must not take the API with it.
- [x] API gaps the web needed: `GET /api/learn`, `GET /api/learn/{key}`,
      `POST /api/learn/{key}/quiz` (writes `education_progress`, which raises
      the Financial DNA knowledge band), and `GET /api/me/summary` — one call
      the dashboard hydrates from, composed from existing builders.
- [x] **Frontend** — Vite + React + TypeScript in `web/`. React Router,
      TanStack Query, a typed API client with refresh-on-401, an auth context,
      a route guard, and eleven pages. No UI library, no CSS framework.
- [x] **Unstyled by design.** `web/src/styles/layout.css` is structure only and
      carries the design tokens declared and left empty behind a
      `/* THEME: user fills this */` block. SPEC section 30's direction (dark,
      green/red/neutral, "trust · clarity · youth") has not been implemented —
      that decision is still open, and guessing at it now would mean throwing
      it away.
- **Done when:** a new user can sign up on the web and complete the full
  SPEC section 36 flow in the browser, in DEMO_MODE, with external APIs and
  Ollama down — and the Telegram bot still passes its own flow unchanged.
  *Verified 2026-09-10 over real HTTP against Postgres with `OLLAMA_HOST`
  pointed at a dead port: signup -> onboarding -> dashboard (62.3/100, five
  components, DNA, one goal at 33.3%) -> what-if (10m -> 15m per month, goal
  date 2027-01-10 -> 2026-12-10) -> purchase (savings 45m -> 0, cover 1.82 ->
  0.91 months) -> time machine -> watchlist (NVDA +15.51%, BTC +4.37%) ->
  learn + quiz -> `/ask`, which returned `source=deterministic` with the
  verified figures. Unauthenticated 401, cross-user 403.*

## Phase 8 — Polish & Deploy  `[x]`
- [x] Visual design for `web/` — the token block in `web/src/styles/layout.css`
      is filled: dark near-black ground, muted slate-blue accent, green/red
      deltas, system fonts only. `contrast.test.ts` computes WCAG ratios from
      the tokens themselves and fails the build below AA, which caught a border
      at 1.27:1 on the way in. Screenshots are generated, not pasted
      (`npm run screenshots`).
- [x] Error handling across all three surfaces. One API envelope
      (`app/api/errors.py`); a 500 carries a request id and nothing else, and
      tests plant a DSN, a token, a balance and a traceback to prove it. The
      web client turns a failed fetch into a sentence rather than a blank
      screen, and a dead session now redirects to login — `AuthContext` was
      never subscribed to `onAuthChange`. The bot audit found no leak path and
      left 19 tests so it stays that way.
- [x] `DEMO_MODE` end-to-end pass with every external service off, both
      surfaces: `scripts/ci_demo.sh`. The model is *unreachable*, not faked —
      a fake would pass while proving nothing about the Phase 5 guarantee.
- [x] Coverage on `app/services/*`: **100%**, statements and branches, floored
      in `.coveragerc`. The gap was five defensive guards; they were tested,
      not refactored away.
- [x] Deployment: `Dockerfile` (multi-stage, non-root, 403 MB),
      `web/Dockerfile` (nginx + static, 74 MB), compose for api + web + db +
      redis with `alembic upgrade head` in the entrypoint and the API waiting
      on the database healthcheck. `docker compose up -d` from a clean checkout
      verified.
- [ ] **Pre-deploy manual checklist — `docs/PRE_DEPLOY.md`. Still open, and
      deliberately so.** A real Alpha Vantage call, a real CoinGecko call, and
      a real OpenAI/Anthropic call if the remote LLM is enabled. All three
      providers are written and their fallbacks are tested; what is unverified
      is whether the live responses still match the shape the parsers expect.
      This machine cannot reach any of them — the same network restriction that
      blocked the qwen2.5:7b pull for two days — so they are a human checklist
      rather than a fake green tick.
- [x] `JWT_SECRET`: `Settings.check_production()` refuses to start outside
      DEMO_MODE on the development default. Verified by hand in all three
      states, and pinned by `tests/api/test_security_posture.py`.
- [x] Rate limiting proven by burst against the running containers, not by
      reading the code: auth throttles at 10/min per address, `/ask` and
      `/simulations` at 20/min per *user* — a different user from the same
      address is unaffected.
- [x] Docs: README rewritten for the current architecture, `docs/DEMO.md` as a
      runbook, screenshots in `docs/screenshots/`.
- [x] Local-model fine-tune notes — `scripts/ft/README.md`. Built, evaluated,
      and **not shipped**: stock `llama3.2:3b` beat it. The pipeline is
      committed and repeatable.

### What is left at the end of the project

One thing, needing a human with network access:

1. **The live-API checks in `docs/PRE_DEPLOY.md`** (above).

Both other items resolved after the project's "done" point:

- **`LOCAL_LLM_MODEL` switched to `qwen2.5:7b`** (2026-09-12), decided without
  the extra 6-8 runs the scorecard called for — the 3-run scores (95% vs 91%)
  were close enough, and the deciding factor was qwen2.5:7b's lower
  safety-downgrade rate (0.67 vs 1.25 per run: it invents fewer figures for
  `safety.enforce` to catch), not the top-line score. Cost: 4.7 GB resident
  instead of 2.0 GB, latency ~2.6s warm (measured, not the predicted 2x).
  Set in `docker-compose.yml`'s `api` service and `.env`/`.env.example`;
  `llama3.2:3b` and the `finmentor-3b` fine-tune both still work by changing
  one value, no code change. See `scripts/ft/README.md` for the full scorecard.
- **The Postgres test-suite guard.** `tests/conftest.py::guard_destructive_target`
  now refuses to run against a Postgres database whose name doesn't contain
  "test" (`FINMENTOR_ALLOW_DESTRUCTIVE_TESTS=1` overrides it). SQLite is
  always exempt. Verified live: pointed at the real `finmentor` database, every
  DB-touching test fails fast before connecting instead of dropping tables.

---

## Legacy prototype

The flat v0 prototype (`ai/`, `analysis/`, `bot/`, `data/`, `education/`,
`finance/`, `config.py`, `main.py`, and the two `tests/test_*.py` files that
covered them) was **removed on 2026-09-08**. Every piece had been ported into
`app/` and re-tested there — the market analytics into
`app/services/market_engine.py`, the budget planner into
`app/services/budget_engine.py`, the education content into
`app/services/education_engine.py`, config into `app/core/config.py` — and
nothing under `app/` or `scripts/` imported it.
