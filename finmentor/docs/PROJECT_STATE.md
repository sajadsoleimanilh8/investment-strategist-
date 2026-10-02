# FinMentor — Project State

**What this file is.** The current, durable state of the project: what is
active, what is decided, what is blocked, and what has been learned the
expensive way. It is the first thing to read when resuming work.

**What it is not.** It is not a build log and not a scope document. Those
exist and remain authoritative for their own purposes:

| Question | Read |
|---|---|
| Why does this exist, what is in scope | [`SPEC.md`](SPEC.md) |
| How was it built, in what order, and why | [`ROADMAP.md`](ROADMAP.md) |
| How is it shaped | [`ARCHITECTURE.md`](ARCHITECTURE.md), [`DATA_MODEL.md`](DATA_MODEL.md) |
| What must a human check before deploying | [`PRE_DEPLOY.md`](PRE_DEPLOY.md) |

Git holds the history. This file holds only what a fresh reader needs in order
to act correctly today.

Last updated against commit `c7058db` plus real quizzes
(uncommitted at time of writing).

---

## Mission

Per [`SPEC.md`](SPEC.md) §1, unchanged. A deterministic financial-intelligence
product for 16-25 year olds: engines compute, AI only explains. No restatement
here, because a second copy of the mission is a second thing to keep in step.

**Mission success criteria: UNKNOWN.** The build plan in `ROADMAP.md` defines
per-phase done conditions and all ten phases are met, but "the project is
successful" is not defined anywhere in the repository. This is an owner
decision, not an inference; nothing below depends on it.

---

## Current focus

**Workstream `audit-remediation` — ACTIVE.**

An end-to-end audit on 2026-09-22 found defects the test suite could not
detect. The remediation is organised in five phases, numbered independently of
the build phases in `ROADMAP.md`.

| Phase | Scope | Status |
|---|---|---|
| 1 | Critical and pre-deployment | **DONE** (`4da8b68`) |
| 2 | Core product and security | **DONE** (`4da8b68`) |
| 3 | Performance and architecture | **DONE** (`P1`-`P7`) |
| 4 | Security hardening | **DONE** (`S2`-`S8`) |
| 5 | Product completeness | **PLANNED** |

### Phase 1 — DONE

Verified: 1258 backend tests passing (13 skipped), 132 frontend, `tsc -b` and
`vite build` clean. Each fix was reverted in turn and the corresponding new
test confirmed to fail.

- Goal-ownership IDOR closed. `PUT /api/goals/{goal_id}` had no ownership
  check at all.
- Structural ownership guard added (`tests/api/test_ownership.py`), which is
  the fix for *why the suite missed it*.
- Bounds on `horizon_months`, all money fields, and the AI question.
- `/api/me/summary` cache write now persists.
- Strict CSP, verified in a browser against the built bundle.

### Phase 2 — DONE

- `planned_budget` and full goal management made functional, restoring two
  health-score components that were frozen. Verified live: score 64.0 → 80.7.
- Logout revokes; AI guards moved into the shared pipeline; OAuth work moved
  off the event loop; `income_type` preserved; error boundary; skip link;
  contrast test now discovers stylesheets.

### Phase 3 — DONE

- **P1 goals N+1.** `_to_out` built a Financial Twin per goal and `load_twin`
  lists the user's goals itself, so the cost grew as the square of the number
  of goals. The twin is now built once per list. Measured: 12 goals went from
  **62 queries to 7**. `tests/api/test_query_counts.py` asserts the shape of
  the cost rather than a number, so an unrelated refactor does not fail it.
- **P2 per-request Redis client** — absorbed into Phase 2. `app/core/limits.py`
  holds one module-level lazy client.
- **P3 provider reuse.** `get_local_provider()` built a fresh `OllamaProvider`
  every call, which made its 30-second availability cache dead code and opened
  a connection per request. Memoised, with a kept-alive `requests.Session`.
- **P4 retention.** `scripts/prune_records.py` bounds `market_snapshots`,
  `password_resets` and `simulations`, scheduled daily.
- **P5 scheduling.** The refresh ran at exactly the cache TTL, which is the one
  interval that guarantees a stale window every cycle; it now runs at
  `MARKET_REFRESH_FRACTION` of it. Both jobs sit behind a Redis lease so
  replicas do the work once.
- **P6 model concurrency.** The 60-second timeout is now 20, and
  `LOCAL_LLM_MAX_CONCURRENCY` caps generations in flight. Past the cap a caller
  is refused immediately and drops to the deterministic tier rather than
  holding a threadpool worker behind a saturated model.
- **P7** duplicate sentence split in `scrub_directives` removed.

### Phase 4 — DONE

- **S2 CSP** and **S8 auth limiter** — done in earlier phases.
- **S3 account-existence oracle.** `login` short-circuited past argon2 for an
  unknown address, and `forgot-password` only reached SMTP for a registered
  one. Both answered the same sentence at measurably different speeds, which
  is the disclosure their own constants exist to prevent. A dummy hash closes
  the login gap; the reset email moved to a background task. One `UPDATE` and
  one `INSERT` of difference remain on the reset path, stated in the route
  rather than hidden.
- **S4 redirect guard.** `_safe_next` rejected `//evil.com` and accepted
  `/\evil.com`, which browsers resolve identically, and the callback page did
  not use the rule at all. Both sides now share one definition, with a
  case table asserted identical across `tests/api/test_security_hardening.py`
  and `web/src/auth/safeNext.test.ts`.
- **S5 handoff replay.** The token was single-use by intention only: the
  cookie was cleared and the signed token stayed valid for its full sixty
  seconds. It now carries a `jti` burned in Redis on first exchange.
- **S6 compose binding.** Postgres and Redis were published on `0.0.0.0` with
  a default password and no password respectively. Both bound to loopback.
- **S7 tracked artefacts.** `bot.err.log`, `.coverage`, a stray lockfile and
  8 MB of demo video are untracked, and `.gitignore` uses patterns rather
  than a list of names. Note: untracking does **not** shrink a clone, because
  history still carries them.

### Code-quality backlog — DONE

The list carried alongside the five phases, now cleared: deprecated UTC
helpers, the unused `days` argument on `store_series`, an unbounded `days`
query parameter, duplicate OpenAPI operation ids, a missing unique constraint
on `chat_sessions` (with a migration that deduplicates first), Alpha Vantage
claiming crypto tickers, the stale transcript list, a confirmation before
removing a watchlist symbol, mobile navigation, two dead components, the
README's test counts, and `100vh` on the app shell.

### Phase 5 — IN PROGRESS

Seven items. Five done, two blocked on the owner.

**Telegram-to-web account linking — DONE.** A code is issued to an
authenticated browser (`POST /api/me/telegram/code`) and redeemed inside
Telegram, by `/link CODE` or a deep link. Twelve characters from an alphabet
with no `O`/`0`, `I`/`1`/`L` or `U`/`V`, SHA-256 hashed, single use, retired
when another is issued, ten minutes. About 59 bits: too much to guess against
the limiter, not enough to shrug at if the table leaks, which is why the TTL
is minutes rather than the hour a reset link gets.

Linking is a **merge**, because the normal case is somebody who used the bot
first and signed up later, so the data they care about is on the bot side.
The rule: *the web account wins every collision; everything that does not
collide moves across.* A collision is exactly the per-user unique
constraints, listed per table in `account_link.MERGED`, asserted against the
schema, with a mapper-registry walk so a table added later cannot be
forgotten. A Telegram account already on another *web* account is refused
rather than merged: that would have to pick which email survives.

**Expense history — DONE.** `replace_expenses` had been filing every save
under a `YYYY-MM` period since the product shipped and rewriting only that
period, so the data was accumulating where nothing could read it.
`GET /api/me/expenses/history` is the read, over a bounded window, in one
statement. A month with no records is **absent, not zero**: zeros would say
the user spent nothing and what we have is no record. No planned-versus-actual
column, because the plan is one current value and not a value per month.

**Income history — DONE.** `income_records` had been in the schema since the
initial migration, described as "the signal behind `income_type = variable`",
with nothing ever writing to it. Profile saves now file the period's income
the same way expenses are filed, and `GET /api/me/income/history` reads it
back with a steadiness measure (coefficient of variation, three periods
minimum).

It does **not** derive `income_type`. Nothing reads that field today, so a
derivation would be a write with no effect; and the moment something does
read it, a silent derivation would move every existing user's figures without
them asking. The panel states what the records look like and points at the
field. See decision 11.

**Structured observability — DONE.** An access log already existed with a
duration and redacted query params, so the gap was narrower than it looked:
it was a sentence rather than fields, it logged the concrete path so
`/api/goals/7` and `/api/goals/8` were separate keys, and `request_id` only
existed inside the error handlers. Now: a JSON formatter behind `LOG_FORMAT`
(compose sets `json`), the matched route's template instead of the path,
`X-Request-ID` on every response, and a `contextvars` request id stamped onto
every record by a `LogRecordFactory` — so a line emitted by the limiter or
the AI layer carries the request it happened in. `require_user` records the
caller, which makes the access log personal data; the retention decision has
to cover it.

**Real quizzes — DONE.** One question per topic became three, with a `why`
per question: the result used to return the topic's `common_mistake` whatever
the user got wrong, which is a sentence about the topic rather than about the
question they missed. Score is the percentage, so 0, 33, 67 or 100, which
fits the 0..100 the progress table already enforced — no migration. A
submission with the wrong number of answers is refused rather than scored,
because padding the gaps invents a failure and scoring only what arrived
would make one answer worth 100%.

`completed` is still set whatever the score, and Financial DNA still counts
`completed` rather than `quiz_score`, so nobody's existing band moved.

The bot's quiz **recorded nothing** before this: tapping through it scored on
screen and wrote no row, so a bot-only user's `financial_knowledge` band
could never move while the bot read `count_completed` to display it. The
scoring and the write now live in `app/api/quiz.py`, which both surfaces
call, and the bot walks the three questions carrying the question index in the
callback payload so a stale button answers the question it was asking.

### Phase 5 — BLOCKED

Account deletion and data export. The prerequisite is unchanged: **the
applicable jurisdiction and retention requirements are UNKNOWN** and must be
established by the owner. Do not infer them. `users_repo.delete` already
cascades correctly, so the mechanism exists; what is missing is what "delete"
has to mean. The access log now holds user ids, so retention covers logs as
well as tables.

---

## Decisions

These materially constrain future work. Each is settled unless the owner
reopens it.

1. **Signing out ends every session, not one device.** There is no device list
   to scope a revocation to, and a per-token denylist would make correctness
   depend on Redis being reachable, which the limiter deliberately does not.
   Users will notice this.
2. **The CSP ships without `'unsafe-inline'`.** Verified empirically against
   the built bundle rather than assumed: React applies inline styles through
   the CSSOM, which CSP does not govern.
3. **HSTS belongs at the TLS terminator**, not in `web/nginx.conf`. On a plain
   `:80` server it is ignored, and a wrong value pins visitors for a year.
4. **The non-finite write guard registers on the SQLAlchemy `Session` class**,
   never on a `sessionmaker`. See Lesson 1.
5. **Absence is not null.** For `planned_budget` and `is_active`, a payload
   that omits the field leaves the stored value alone; an explicit null or
   value changes it. Without this, a client round-tripping what it was given
   erases fields it never knew about.
6. **Guards live in the shared pipeline, never on a delivery surface.**
   `ask_pipeline.guard` owns the AI length cap and rate budget; the HTTP route
   and the Telegram bot only translate its refusal.
7. **The rate limiter fails open for `ask` and closed for `auth`.** Losing the
   limiter on `/ask` costs money; losing it on authentication is the attack.
8. **A model generation past the concurrency ceiling is refused, not queued.**
   Waiting for a slot holds a threadpool worker for the length of somebody
   else's generation, which is the stall the ceiling exists to prevent.
   `LocalLLMUnavailable` is a signal the AI layer already handles, so the
   caller gets verified figures instead of a wait.
9. **Scheduled jobs run without a lease when Redis is unreachable.** Duplicated
   work is a cost; no work at all is an outage, and this project deploys one
   API container. Same direction as the `ask` limiter.
10. **Retention for `simulations` is a runaway guard, not a policy.** The
    default (500 per user) is far above anything the product can reach, and the
    newest runs are never removed. Deleting a user's own saved runs is an
    owner decision; the number is a setting.
11. **A derived `income_type` is shown, never written.** Recorded income
    gives a steadiness signal, and the user's declared value stays theirs.
    Nothing reads `income_type` today, so writing a derived value would have
    no effect; the moment something does, a silent derivation would move
    every existing user's figures without them asking. An observation they
    can act on is better than a score that changed by itself.
12. **A quiz is a comprehension check, not an exam.** Three questions now,
    and `completed` is still set whatever the score. Financial DNA counts
    completion rather than the score, which is also what kept the richer
    quiz from moving anybody's existing band.

---

## Constraints

- **Any new route naming a record must be guarded or declared.** A route with
  a `{*_id}` path parameter or a body field ending in `_id` must either depend
  on `owned_user_id` or appear in `tests/api/test_ownership.py::OWNERSHIP`
  with a real cross-user attack. The test walks the router tree, so forgetting
  fails CI on the day the route is written.
- **Money is finite and bounded**: `0 <= v <= 1e12`. Percentage levers
  `-1 <= d <= 100`. `horizon_months` `1..600`. Enforced at the schema and again
  at session flush, because the bot and the scripts never pass through Pydantic.
- **No em-dashes in user-visible copy** (web, engine, bot, AI prompts). Code
  comments and docstrings are deliberately exempt.
- **The engine computes; AI only explains.** Unchanged from `SPEC.md`, restated
  because every audit phase was checked against it.

---

## Lessons and negative evidence

Kept because they are expensive to rediscover, not as a record of what happened.

1. **SQLAlchemy keys its event registry on `id()`.** Registering a listener on
   a per-test `sessionmaker` silently no-ops when a collected factory's address
   is recycled. Cost: the non-finite write guard was absent from roughly half
   the test suite while the suite was green. Register on the `Session` class.
2. **One green run proves less than it looks** when registration is
   id-dependent. The defect above surfaced as a single intermittent failure and
   then three clean runs. Run the suite repeatedly before trusting a fix to
   anything registration-shaped.
3. **The `client` fixture waives ownership** (`require_user`, `owned_user_id`
   and `assert_owns` are all overridden), so ownership defects are structurally
   invisible to almost every test. This is why the IDOR shipped. Cross-user
   work belongs in `test_ownership.py` or `test_auth.py`, which use
   `raw_client` and real tokens.
4. **Browser automation's `form_input` bypasses React's synthetic events**, so
   values set that way never reach component state. Use it to verify rendering
   and interaction; assert request payloads with component tests instead.
5. **A fixture with a hardcoded period expires.** `test_goals.py` pinned
   expenses to `"2026-09"` and compared an ETA against `date.today()`. It
   passed for as long as the calendar agreed and then broke on 1 October, as
   `load_twin` reads the *current* period and so saw no expenses at all. Any
   fixture date compared against today should be derived from today.

6. **`get_db` does not commit, so every write route must.** Obvious once
   stated, and `POST /api/me/telegram/code` shipped without it during this
   phase: the user was handed a code that had already been rolled back, and
   every redemption said "that code is not valid". The suite could not see it
   because the `db` fixture gives the app and the assertions *the same
   uncommitted session*, so a missing commit is invisible to almost every API
   test. Found by driving a real API against a real database instead.
   `test_architecture_guards.py::test_every_write_route_owns_its_transaction`
   now walks the route modules and fails on a writing method with no commit.
7. **The limiter's window is fixed, not rolling.**
   `limits._LocalCounter.hit` buckets by `int(time.time() // 60)`, a
   wall-clock minute. Any test that counts requests up to a limit therefore
   fails whenever it happens to straddle a `:00` — rare per run, certain over
   enough runs. Pin the clock in such a test (`tests/api/test_telegram_link.py`
   has the fixture) rather than trusting a fast loop to stay inside one
   window. Found exactly as lesson 2 predicts: green alone, green in its own
   file, red once in a full run.

---

## Blockers

- **The pull request is not open.** Branch
  `fix/phase-1-2-security-and-product-defects` is pushed (`9765c89`); the `gh`
  CLI is not installed on this machine. Open it from
  `https://github.com/sajadsoleimanilh8/investment-strategist-/compare/main...fix/phase-1-2-security-and-product-defects`
  or install `gh`.

---

## Needs verification

Unresolved because they need infrastructure this machine does not have. None
is an inference to be settled by reasoning.

| Item | Why it is open |
|---|---|
| nginx `envsubst` substitution of `CSP_CONNECT_SRC` in the real container | The image was never run here. Fails loudly, not silently: a literal `${CSP_CONNECT_SRC}` breaks API calls at deploy. |
| Pre-existing `Infinity` rows on a long-lived database | Reads of such a row now raise rather than return nulls. Fresh deployments are unaffected; an old database wants a one-off scan. |
| The three live external APIs, HTTPS, and a restored backup | Pre-existing and unchanged. See [`PRE_DEPLOY.md`](PRE_DEPLOY.md). |

---

## Open owner decisions

Only genuine decisions, smallest first.

1. **Is mission success defined?** See the Mission section. Nothing currently
   blocks on it.
2. **Should this repository have an `AGENTS.md`?** There is none. The
   conventions that would go in it (the ownership rule, the bounds, the
   em-dash rule) are recorded above and enforced by tests, so one would be
   organisational rather than load-bearing. Not created, to avoid inventing
   conventions the repository has not agreed.
