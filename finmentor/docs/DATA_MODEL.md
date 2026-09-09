# FinMentor — Data model

PostgreSQL + SQLAlchemy 2.0 + Alembic. Minimal PII (Telegram id + locale).

| Table | Purpose | Key fields |
|---|---|---|
| `users` | identity | telegram_id, locale, risk_profile |
| `financial_profiles` | 1:1 with user | monthly_income, income_type, current_savings, debt, monthly_debt_payment, emergency_fund, planned_budget_json |
| `income_records` | history for variable income | amount, period, source |
| `expense_records` | monthly expenses by category | category, amount, period, is_essential |
| `financial_goals` | goals | name, target_amount, current_amount, deadline, priority, is_active |
| `watchlists` | user market watchlist | user_id, symbol |
| `market_assets` | known assets | symbol, provider_id, asset_class, display_name, is_active |
| `market_snapshots` | cached price series | symbol, as_of, points_json |
| `simulations` | saved scenarios | kind (`what_if`/`time_machine`/`decision`), params_json, result_json |
| `chat_sessions` | AI transcript | transcript_json |
| `education_progress` | /learn progress | topic_key, completed, quiz_score |

Derived objects (NOT stored, recomputed on demand): Financial Twin, Health
Score, Financial DNA. The DNA traits are `saving_discipline`,
`emergency_readiness`, `debt_management`, `goal_discipline`, `budget_stability`
(Strong / Moderate / Weak, Strong always being the healthy end) plus
`financial_knowledge` (Beginner / Intermediate / Advanced).

Budget stability compares that period's `expense_records` against
`financial_profiles.planned_budget_json` (the planned per-category snapshot).
Both are carried into the Financial Twin; `app/services/health_score.py` owns
the formula. A user with no planned budget scores the documented neutral 12/20.

Conventions (phase 1):

- Amounts are `double precision`, matching the float contracts in
  `app/schemas/finance.py` — the engine never sees `Decimal`.
- `period` is a `YYYY-MM` string; expenses are unique per
  (user, period, category), so a month's breakdown is overwritten, not appended.
- Every user-owned table has `ON DELETE CASCADE` and a matching ORM relationship
  on `User`, so deleting a user removes all of their data.
- `*_json` columns hold `json.dumps` text, not `JSONB`.
- `market_snapshots` has no `days` column: a snapshot is keyed by symbol
  and satisfies any request for that many days or fewer. Asking for a
  longer window is a cache miss and replaces the row.
  `app/repositories/simulations.py` owns that encode/decode, so callers pass and
  receive plain dicts; `result_json` stores the engine output verbatim, which is
  what makes a saved run reproducible without re-running it.
- Enum-like columns (risk profile, income type, expense category, asset class,
  simulation kind) are guarded by CHECK constraints.
- Schema lives in `migrations/versions/`; `alembic check` must report no drift.
