# FinMentor — Product & Engineering Specification

> Polished from the original brief. Source of truth for scope; the phase plan
> in [`ROADMAP.md`](ROADMAP.md) sequences the build.

## 1. Vision

FinMentor helps young adults (16–25, beginner/intermediate financial
literacy: students, young employees, freelancers) understand:

1. Where their money goes
2. How financially healthy they are
3. Whether they are progressing toward their goals
4. What would happen if they changed a financial behaviour
5. How markets have recently behaved
6. Basic financial concepts

Positioning: **FinMentor — Your Financial Twin. Understand your money.
Simulate your future.** It answers *"if I make this decision, what could
happen to my finances?"* — not *"what should I buy?"*

## 2. Core differentiator

Financial Twin + Health Score + What-if Simulator + Time Machine +
deterministic engine + conversational AI layer + clarity-first UX +
local-first AI + market-trend context without personalised investment advice.
It should feel like a **financial decision simulator**, not a ChatGPT wrapper.

## 3. Architectural rule (non-negotiable)

    User -> intent detection -> structured params -> deterministic engine
         -> verified result -> LLM explanation -> User

The LLM must never: invent prices/percentages/market data, compute financial
scores, generate fake history, make guaranteed predictions, or give
personalised buy/sell instructions. All important numbers come from
`app/services/*`. See [`ARCHITECTURE.md`](ARCHITECTURE.md).

## 4. Modules

### A. Onboarding
- Income: amount + type (fixed / variable / mixed)
- Expenses by category: housing, food, transportation, education, bills,
  entertainment, shopping, other (each flagged essential / discretionary)
- Position: current savings, debt, monthly debt payment, emergency fund
- Goals: name, target amount, current amount, deadline, priority
- Risk profile: a few educational questions -> conservative / moderate /
  aggressive. **Not** presented as a licensed suitability assessment.

### 5. Financial Twin
Deterministic snapshot object, recomputed on any relevant data change:

```json
{
  "income": 30000000, "monthly_expenses": 18000000, "monthly_savings": 12000000,
  "current_savings": 45000000, "debt": 10000000, "emergency_fund": 30000000,
  "goals": [], "risk_profile": "moderate"
}
```

### 6. Financial Health Score (0–100)
Centralised formula in `app/services/health_score.py`. Five components x 20:

| Component | Metric |
|---|---|
| Savings Rate | `monthly_savings / monthly_income` |
| Emergency Fund | `emergency_fund / essential_monthly_expenses` (months) |
| Debt Load | debt-to-income burden |
| Budget Stability | consistency of actual vs planned spending |
| Goal Progress | progress across active goals |

Rendered like:

```
Financial Health Score: 74/100
Savings Rate     17/20      Budget Stability   16/20
Emergency Fund   12/20      Goal Progress      14/20
Debt Load        15/20
```

### 7. Financial DNA
Human-readable bands from the same metrics: Saving Discipline, Emergency
Readiness, Debt Management, Goal Discipline, Budget Stability (Strong /
Moderate / Weak) + Financial Knowledge (Beginner / Intermediate / Advanced).
Rule-generated; AI narrates.

### 8. What-if Simulator
Parse scenario -> structured params -> deterministic recompute -> compare
current vs simulated -> AI explains. Supported deltas: monthly-savings delta,
income %, expense %, per-category expense delta, one-time purchase.

```
CURRENT   savings 4M   goal 42%   ETA Mar 2027
SCENARIO  savings 7M
RESULT    savings +3M  goal 42%->61%  ETA Mar 2027 -> Dec 2026
```

### 9. Financial Time Machine
Compare named paths — current / conservative / improved-savings /
increased-expense — over a horizon. For each: projected savings, goal
progress, emergency coverage, estimated goal date. Language: *"Illustrative
projection based on the assumptions you entered."*

### 10. Decision Simulator
Evaluate a real purchase: show savings before/after, emergency coverage
before/after, health score before/after, affordability. AI explains
consequences; never says "don't buy it".

### 11–13. Market Intelligence
- `MarketDataProvider` abstraction: `AlphaVantageProvider` (equities),
  `CoinGeckoProvider` (crypto), `MockMarketProvider` (fallback / demo).
  Auto-fallback to mock on any failure.
- Analytics (deterministic): daily / 7d / 30d % change, short & long moving
  average, daily-return volatility, rule-based trend
  (`short_MA > long_MA -> Upward`, etc.). Never called a prediction.
- `/watchlist`: add / remove / view / rank by recent movement. Labels make
  clear historical movement is not a forecast.

### 14. AI Mentor (`/ask`)
Answers education + Financial Twin questions. Receives structured context
(health score, savings rate, emergency months, active goals, market context)
and never invents missing values — says when data is unavailable.

**Tone.** The mentor is a warm, encouraging guide for a 16-25 year old who is
new to money, not a form and not an advisor: short paragraphs, no jargon
without a plain-English line beside it, what is going well before what is
weak, and never a lecture about how someone spends. The persona lives in
`SYSTEM_PROMPT` *below* the safety rules, because a small model weights the
top of its prompt hardest and warmth is never worth a wrong number.

**Two shapes of answer.** A message the parser reads (health, what-if,
decision, market, education) gets the precise path: one engine call, one
context object, no conversation history, so the same question always produces
the same answer. Anything else — "i want to save for a car", "thanks, what
next?" — goes to the guide, which receives a *snapshot* of figures the engine
already computed plus the last few turns, and replies conversationally. Both
shapes pass through the same safety layer (section 16); the guide gets no
latitude on numbers for being friendly.

### 15. Hybrid AI
`local LLM -> optional remote LLM -> synthesizer`. Local is default and the
reliable core. Config-driven (`LOCAL_LLM_*`, `REMOTE_LLM_*`), no hard-coded
model. Remote failure -> local. Local failure -> deterministic passthrough.
The app never crashes because an AI provider is down.

### 16. AI safety layer
Separates the deterministic engine from the explanation layer. Market
responses carry: *"This information describes recent or historical market
behaviour and is not a prediction or personalised investment recommendation."*

### 17. Education (`/learn`)
12 topics: budgeting, emergency fund, savings rate, inflation, risk,
volatility, diversification, compound growth, time horizon, debt, opportunity
cost, investment basics. Each: simple explanation, example, common mistake,
mini quiz. Curated content, not AI-generated.

### 18. Budget (`/budget`)
50 / 30 / 20 as an adjustable **guideline**, not a universal truth. User can
customise the split.

### 19. Interfaces
Two delivery surfaces over one FastAPI backend; all business logic stays
server-side.

**Telegram bot** (ships first — ROADMAP Phase 6). Commands: `/start /profile
/health /budget /goals /simulate /market /watchlist /learn /ask /help`. Inline
keyboards everywhere; minimise typing. Identity = Telegram user id, no login.

**Web app** (ROADMAP Phase 7). Same features as a dark financial dashboard
(§30). Requires real auth — signup / login, hashed passwords, JWT or session
cookies (`app/core/security.py`); `users` gains `email` + `password_hash`. A
user only ever sees their own data. The frontend calls the documented API and
holds no logic of its own.

Plain English, simple terminology, on both.

## 20. Data model
See [`DATA_MODEL.md`](DATA_MODEL.md). PostgreSQL + SQLAlchemy + Alembic.

## 21. Backend
Python 3.11, FastAPI, PostgreSQL, SQLAlchemy 2.0, Pydantic v2, Redis
(optional), APScheduler (optional), Ollama. Clean architecture — see
`README.md` layout.

## 22. API endpoints (minimum)

```
POST /api/users                        GET  /api/users/{id}
GET  /api/financial-profile/{id}       PUT  /api/financial-profile/{id}
GET  /api/health/{id}
GET  /api/goals/{id}                   POST /api/goals            PUT /api/goals/{goal_id}
POST /api/simulations                  GET  /api/simulations/{user_id}
GET  /api/market/assets                GET  /api/market/assets/{symbol}
GET  /api/market/watchlist/{user_id}
POST /api/ai/ask
```

## 23. Performance targets
Deterministic calc < 500 ms; DB ops < 300 ms typical; simple API < 1 s;
simulation < 1 s. `/budget`, `/health`, `/goals` must not invoke an LLM.

## 24. Caching
Scheduled market fetch -> DB / Redis -> users. No external market call on the
per-request path once warm.

## 25. Demo mode (`DEMO_MODE=true`)
Synthetic deterministic market data, local LLM if present, seeded demo user.
Entire product demonstrable offline; never looks broken.

## 26. Security
Env-var secrets, input validation, rate limiting, ORM (no raw SQL), no keys
in source, minimal data collection. Never log keys, tokens, or financial PII.

## 27. Responsible UX
Short disclaimer in every market section: *"FinMentor provides educational
information and historical market analysis. It does not provide personalised
investment advice or guarantee future returns."* No exaggerated claims.

## 28. Testing
Unit: savings rate, emergency fund, debt burden, health score, goal progress,
budget allocation, scenario simulation, % change, moving averages,
volatility, trend classification. AI fallback: remote up -> hybrid;
remote down -> local; local down -> graceful. API: all major endpoints.

## 29. Demo user
Income 30M, expenses 18M, savings 45M, emergency 30M, debt 10M; goal Laptop
target 60M / current 20M / 6 months. Showcases health, DNA, goal progress,
what-if, decision sim, market watch, AI explanation.

## 30. UI design
Modern dark financial dashboard. Clean cards, strong typography, minimal
gradients. Green = positive, red = warning, neutral = informational. Not a
crypto trading terminal. Communicates trust, intelligence, simplicity, youth,
clarity.

## 31. Language
**English-only product.** All user-facing copy — bot replies, education
content, disclaimers, Financial DNA labels, error messages — is plain,
beginner-friendly English (LTR). Code, identifiers, comments, docs, and API
schemas are English too. No localisation layer is required for the MVP;
strings live directly in `app/bot/messages.py`, `app/ai/safety.py`, and
`app/services/education_engine.py`. Currency is rendered via a configurable
symbol (`settings.currency_symbol`, default `$`) rather than a hard-coded
unit.

## 32. AI system prompt
See `app/ai/prompts.py::SYSTEM_PROMPT` — the only place prompt text lives.
Kept short and imperative because the default local model is a 3B: long prompts
make small models drift, and drift here means an invented number. The safety
layer (`app/ai/safety.py`) is the backstop, not the prompt.

## 36. Definition of Done (MVP)
A new user can: `/start` -> create profile -> see Health -> see DNA -> create
goal -> run what-if -> evaluate a purchase -> view market trends -> ask AI to
explain — **with remote AI and external market APIs unavailable.**
