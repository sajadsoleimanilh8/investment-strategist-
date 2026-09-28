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

Last updated against commit `4da8b68`.

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
| 3 | Performance and architecture | **PLANNED**, partially absorbed |
| 4 | Security hardening | **ACTIVE**, partially done |
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

### Phase 3 — PLANNED, two items already absorbed

Completed early because Phase 2 work touched the same code:

- **P2 (per-request Redis client)** — done. `app/core/limits.py` holds one
  module-level lazy client.
- **P8 (auth fail-open)**, listed under Phase 4 as S8 — done. The `auth`
  bucket falls back to an in-process counter.

Still open: P1 goals N+1 (`_to_out` builds a twin per goal), P3 memoise
`OllamaProvider`, P4 retention for `market_snapshots` / `simulations` /
`password_resets`, P5 scheduler placement and refresh interval, P6 Ollama
timeout and concurrency, P7 duplicate sentence split in `scrub_directives`.

### Phase 4 — ACTIVE

Done: S2 (CSP), S8 (auth limiter).
Open: S3 account-existence timing oracle, S4 client-side OAuth `next`
validation, S5 single-use handoff token, S6 compose port binding, S7 tracked
runtime logs and `.gitignore`.

### Phase 5 — PLANNED

Account deletion, data export, Telegram-to-web account linking, expense
history, income history, real quizzes, structured observability.

Account deletion and export have a prerequisite: **the applicable jurisdiction
and retention requirements are UNKNOWN** and must be established by the owner
before implementation. Do not infer them.

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

---

## Blockers

- **The pull request is not open.** Branch
  `fix/phase-1-2-security-and-product-defects` is pushed (`4da8b68`); the `gh`
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
