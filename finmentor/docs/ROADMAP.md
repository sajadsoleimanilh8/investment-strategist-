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
- **`LOCAL_LLM_MODEL` stays a plain env var.** No model tag is hard-coded
  outside `config.py`, and a test asserts it.

## Phase 7 — Website

FinMentor is not Telegram-only. The web app is a second delivery surface over
the **same** FastAPI backend — `app/services`, `app/ai`, `app/market`,
`app/api` are reused unchanged. Telegram keeps working throughout.

- [ ] **Auth** — build out `app/core/security.py`: signup / login, password
      hashing (argon2/bcrypt), JWT access + refresh (or session cookies), an
      `require_user` FastAPI dependency. Add `email` + `password_hash` to
      `users` (Alembic migration). Telegram users stay keyed by `telegram_id`;
      a row can have both.
- [ ] Guard every `/api/*` route (except signup/login/healthz) with
      `require_user`; a user only reads/writes their own data.
- [ ] CORS config; rate limiting (Redis) on `/api/ai/ask` and `/api/simulations`.
- [ ] Fill API gaps the web needs: expose the Time Machine, education
      content listing + quiz submission, full profile/expense editing,
      watchlist mutation (some exist bot-only today).
- [ ] Frontend — stack decision (Next.js / SvelteKit / Vite+React), then the
      dashboard per SPEC §30 (dark, green/red/neutral, "trust · clarity ·
      youth"): onboarding, Financial Health + DNA, goals, What-if + Decision
      simulators, Time Machine, Market watch, Ask AI, Learn.
- [ ] Frontend talks only to the documented API — no business logic in the
      client, same rule as the bot.
- **Done when:** a new user can sign up on the web and complete the full
  SPEC §36 flow in the browser, in DEMO_MODE, with external APIs and Ollama
  down — and the Telegram bot still passes its own §36 flow unchanged.

## Phase 8 — Polish & Deploy
- [ ] Error handling + user-friendly messages everywhere (bot + web + API)
- [ ] `DEMO_MODE` end-to-end pass with all external services off (CI check)
- [ ] Full test suite green in CI; coverage on `app/services/*`
- [ ] Deployment: Dockerfile(s), compose for api + web + db + redis,
      `alembic upgrade` on boot
- [ ] Pre-deploy manual checklist: real Alpha Vantage / CoinGecko keys, real
      OpenAI/Anthropic call if remote LLM is enabled
- [ ] Docs: finalise README, add screenshots / demo script
- [ ] Optional: local-model fine-tune notes (financial tone / accuracy)

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
