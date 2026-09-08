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

## Phase 3 — Simulation
- [ ] `simulation_engine.apply_scenario` + `project` (straight-line)
- [ ] `simulation_engine.run_what_if` -> `SimulationOut` with deltas
- [ ] `time_machine.compare_paths` over the 4 presets
- [ ] `decision_simulator.evaluate_purchase`
- [ ] `ai/intent.parse` — English number/percent parsing ("5M", "5 million",
      "15%"), intent routing (rule-first; LLM fallback constrained to the schema)
- [ ] `POST /api/simulations`, `GET /api/simulations/{user_id}` (+ persist to `simulations`)
- [ ] Unit tests: scenario maths, projection, decision sim, parser fixtures
- **Done when:** "what if I save $5M more each month?" -> parsed params ->
  numeric before/after + goal-date shift, no LLM doing arithmetic.

## Phase 4 — Market
- [ ] `market/cache.py` read-through cache -> `market_snapshots` (+ optional Redis)
- [ ] APScheduler job in `app/main.py` lifespan; `scripts/fetch_market_snapshots.py`
- [ ] Real `AlphaVantageProvider` / `CoinGeckoProvider` verified against live APIs
- [ ] Watchlist CRUD + `market_assets` seed list
- [ ] Endpoints: `GET /api/market/assets`, `/api/market/assets/{symbol}`,
      `/api/market/watchlist/{user_id}`
- [ ] Disclaimer on every market payload (schema default already present)
- [ ] Tests: cache hit/miss, provider fallback to mock, ranking
- **Done when:** `/market` works live AND with network off (mock), cache keeps
  external calls off the request path.

## Phase 5 — AI
- [ ] `ai/local_llm.py` verified against a running Ollama model
- [ ] `ai/remote_llm.py` verified for openai + anthropic; returns None on failure
- [ ] `ai/synthesizer.explain` — context-only prompting, hybrid merge
- [ ] `ai/safety.enforce` — disclaimer once, strip buy/sell imperatives,
      detect numbers absent from context
- [ ] `POST /api/ai/ask` — assembles deterministic context, never lets LLM compute
- [ ] Tests: remote-up -> hybrid, remote-down -> local, local-down -> deterministic
      passthrough; safety scrubbing; "data unavailable" path
- **Done when:** `/ask` explains a real health score / simulation with all three
  fallback tiers covered by tests.

## Phase 6 — Telegram
- [ ] Onboarding conversation (income -> expenses -> position -> goals -> risk)
- [ ] All commands + inline-keyboard callback router (`app/bot/keyboards.py`)
- [ ] English copy in `app/bot/messages.py`; number formatting via `formatting.py`
- [ ] Wire each command to services/AI; loading states ("Calculating…")
- [ ] Port/retire legacy `bot/`, `main.py`, top-level `config.py`
- **Done when:** the full Definition-of-Done flow works from Telegram in DEMO_MODE.

## Phase 7 — Polish
- [ ] Error handling + user-friendly messages everywhere
- [ ] Rate limiting (Redis) on `/ask` and simulation endpoints
- [ ] `DEMO_MODE` end-to-end pass with all external services off (CI check)
- [ ] Full test suite green in CI; coverage on `app/services/*`
- [ ] Deployment: Dockerfile, compose for app+db+redis, `alembic upgrade` on boot
- [ ] Docs: finalise README, add screenshots / demo script
- [ ] Optional: local-model fine-tune notes (financial tone / accuracy)

---

## Legacy → app/ port checklist
| Legacy file | Ported to | Phase | Status |
|---|---|---|---|
| `analysis/technical_indicators.py` | `app/services/market_engine.py` | 0 | `[x]` |
| `finance/budget_planner.py` | `app/services/budget_engine.py` | 0 | `[x]` |
| `data/market_data.py` | `app/market/{alpha_vantage,coingecko,mock_provider}.py` | 0/4 | `[~]` |
| `ai/local_model.py` | `app/ai/local_llm.py` | 0/5 | `[~]` |
| `ai/api_model.py` | `app/ai/remote_llm.py` | 0/5 | `[~]` |
| `ai/combiner.py` | `app/ai/synthesizer.py` | 0/5 | `[~]` |
| `education/qa_content.py` | `app/services/education_engine.py` | 0/2 | `[x]` |
| `bot/handlers.py`, `bot/telegram_bot.py` | `app/bot/*` | 6 | `[ ]` |
| `config.py` | `app/core/config.py` | 0/6 | `[~]` |
| `main.py` | `app/bot/main.py` + `app/main.py` | 0/6 | `[~]` |
| `tests/test_*` | `tests/unit/test_*` | 0 | `[x]` (new copies) |

Delete a legacy file only after its row is `[x]` and nothing imports it.
