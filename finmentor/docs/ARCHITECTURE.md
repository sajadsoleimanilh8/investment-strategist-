# FinMentor — Architecture

## The one rule

    User
     -> Intent detection            (app/ai/intent.py)
     -> Structured params            (app/schemas/*)
     -> Deterministic engine         (app/services/*)   <-- ALL numbers decided here
     -> Verified result
     -> LLM explanation layer        (app/ai/synthesizer.py -> safety.py)
     -> User

Never `User -> LLM -> Answer`. The LLM never calculates a score, a projection,
a percentage, or a market number. It receives the deterministic result as
context and turns it into plain-English prose.

## Layers

| Layer | Package | Depends on | AI? |
|---|---|---|---|
| Delivery | `app/bot`, `app/api`, `web/` | services, ai | no |
| Explanation | `app/ai` | services (schemas only) | yes |
| Engine | `app/services` | schemas, market | **no** |
| Market data | `app/market` | core | no |
| Persistence | `app/models`, `app/db` | core | no |
| Config/infra | `app/core` | — | no |

## Two surfaces, one API

    Telegram  ->  app/bot  ---+
                              |--> app/api/ask.py, app/api/deps.py -> engine
    Browser   ->  web/  --HTTP-+   (app/api/routes/*)

Both surfaces answer questions through the *same* `app/api/ask.answer_question`,
so there is one implementation of the architectural rule rather than two that
drift. The difference is how they get there: the bot resolves a user from the
Telegram update and calls the pipeline in-process, while the browser sends a
bearer token over HTTP.

That difference is why adding authentication in Phase 7 could not break the
bot — it makes no HTTP calls, and a test asserts as much.

## The auth boundary

    signup / login / refresh / logout / healthz    open
    everything else under /api                     require_user -> 401
    routes taking {user_id}                        OwnedUserId  -> 403
    routes taking a user id in the body            assert_owns  -> 403

`require_user` is attached to the *router*, not to individual routes, so a
route added later is guarded by default rather than by remembering. A user row
carries `telegram_id`, `email`, or both; a CHECK constraint requires at least
one.

Access tokens are 30 minutes and cannot be revoked — that is what makes them
short. Refresh tokens are 14 days and rotate on every use, so a stolen one stops
working the moment the real user refreshes. The `typ` claim is checked in both
directions: without it, a refresh token presented as an access token would
quietly make every session fourteen days long.

## Hybrid AI

    local LLM (Ollama, default, always tried)
        + optional remote LLM (only if REMOTE_LLM_ENABLED and reachable)
        -> merged by the local model
        -> safety.enforce() adds disclaimer, strips prediction/buy-sell claims

Failure modes:
- remote down  -> local only (normal)
- local down   -> return deterministic context verbatim + disclaimer (never crash)

## Demo mode (`DEMO_MODE=true`)

- market: `MockMarketProvider` only (seeded, deterministic, offline)
- AI: local if present, else deterministic passthrough
- data: seeded demo user (`scripts/seed_demo_user.py`)

The whole Definition-of-Done flow must pass with no external APIs.
