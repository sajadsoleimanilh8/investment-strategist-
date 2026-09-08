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
| Delivery | `app/bot`, `app/api` | services, ai | no |
| Explanation | `app/ai` | services (schemas only) | yes |
| Engine | `app/services` | schemas, market | **no** |
| Market data | `app/market` | core | no |
| Persistence | `app/models`, `app/db` | core | no |
| Config/infra | `app/core` | — | no |

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
