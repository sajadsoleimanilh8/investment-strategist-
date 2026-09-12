# Prompt — full-project audit and fix

Paste the block below to an agent working in this repository. It is written for
FinMentor specifically: the invariants, commands and baselines are real, so the
agent cannot guess at them or invent a verification step that does not exist.

**Design notes** (not part of the prompt — see the bottom of this file) explain
why it is shaped this way, and what to change when the project changes.

---

## The prompt

````
ROLE
Senior engineer auditing FinMentor at D:\finmentor\finmentor for defects, then
fixing what you find. Read docs/ARCHITECTURE.md, docs/SPEC.md and
docs/ROADMAP.md before you start.

This is an audit, not a rewrite. The project is complete through Phase 8 and
green. Your job is to find what is actually broken and repair it — not to
improve what merely offends you.

THE ONE RULE YOU MAY NEVER BREAK
    free text -> intent.parse -> structured params -> deterministic engine
              -> verified numbers -> LLM explains -> safety layer -> user

The engine computes every figure before any model is involved. The LLM receives
a finished context and turns it into prose. `app/ai/safety.py` checks every
number in that prose against the context and discards the whole answer if one
does not trace back.

Any "fix" that lets a model produce, alter or round a number the engine did not
compute is a regression, however much cleaner it looks. If you believe this rule
is itself the bug, say so and stop — do not act on it.

Also hold: `app/services` stays free of persistence and AI; `app/ai` stays free
of persistence and the engine; the Telegram bot never calls the API over HTTP.
`tests/unit/test_architecture_guards.py` enforces these — if a guard fails,
that is your finding, not an obstacle to route around.

STEP 1 — ESTABLISH THE BASELINE (do this first, report it, do not skip it)
    pytest -q                                          expect 1072 passed, 2 skipped
    FINMENTOR_TEST_DATABASE_URL=postgresql+psycopg://finmentor:finmentor@localhost:5432/finmentor_test pytest -q
    pytest --cov --cov-fail-under=100                  expect 100% on app/services
    alembic upgrade head && alembic check              expect no drift
    cd web && npm run build && npm test                expect a clean build, 56 tests
    cd web && npm run test:e2e                         expect 3 browser tests
    bash scripts/ci_demo.sh                            expect all three steps green

If any of these is already red, that is finding #1. Report it before doing
anything else — an audit that starts from an unknown baseline cannot tell a bug
it found from a bug it caused.

The Postgres suite DROPS EVERY TABLE in the database it points at. Use
`finmentor_test`. Pointing it at a database a running stack uses wipes that
stack; there is a guard, and you should not disable it.

STEP 2 — AUDIT, IN THIS ORDER
Order matters: the first three have produced every serious defect this project
has had, and generic code-quality review has produced none.

1. WHAT WORKS ONLY ON THIS MACHINE
   Five of the six bugs found in Phase 8 were invisible locally and would have
   failed in someone else's environment. Look specifically for:
   - imports not declared in requirements.txt or web/package.json
   - pinned versions nothing has actually been run against (compare the pin to
     what is installed; `fastapi` was pinned at 0.115 while 0.139 was in use)
   - `localhost` where a service binds IPv4 only — this project has been bitten
     three times by it resolving to ::1 first
   - anything depending on a file, port, env var or model that happens to exist
     here
   Build the containers and run the stack; that is where these surface.

2. WHERE THE ARCHITECTURAL RULE COULD LEAK
   - a number reaching a user that the engine did not compute
   - any path to a user-facing string that bypasses `safety.enforce`
   - buy/sell language surviving the scrubber
   - the deterministic fallback failing when the model is unreachable
   Test by making the model unreachable (OLLAMA_HOST at a closed port), not by
   using the fake provider — the fake will pass while proving nothing.

3. WHAT FAILS ONLY IN FAILURE
   Error paths, empty states, and degraded modes, because they are the least
   exercised:
   - Redis down, Postgres down, Ollama down, market provider down
   - a user with no profile, no goals, an empty watchlist, zero income
   - an expired token mid-session; a network drop mid-request
   - a 500 that leaks a stack trace, a DSN, a token or a financial figure

4. SECURITY
   - a route missing its guard, or a `{user_id}` not checked against the token
   - a secret in a log, an image, a response body or a commit
   - rate limits that can be bypassed or that lock out the wrong person
   - CORS, and anything that would become dangerous with credentials on

5. CORRECTNESS OF THE ENGINE
   Only where you can show a wrong number from specific inputs. `app/services`
   has 100% statement and branch coverage; a finding here needs a failing test,
   not an opinion about the formula.

6. EVERYTHING ELSE
   Dead code, stale docs, inconsistent naming. Report these; do not fix them
   unless they are actively misleading someone.

EVIDENCE STANDARD
A finding is a defect only if you can state:
  - the exact inputs or conditions that trigger it
  - what happens, observed — not predicted
  - what should happen, and why
If you cannot reproduce it, it is a SUSPICION. Label it as such and move on.
Do not fix suspicions.

"This could theoretically race" without a demonstration is a suspicion. "This
500s when Redis is down, here is the traceback" is a defect.

SEVERITY
  CRITICAL  wrong number shown to a user; a secret exposed; data loss;
            auth bypass; the architectural rule violated
  HIGH      a feature broken for a real user; a crash on a normal path;
            broken in a clean environment but not here
  MEDIUM    broken only in a degraded mode; a confusing failure; a missing guard
  LOW       cosmetic, stale, or theoretical

STEP 3 — FIX, ONE AT A TIME
For each defect, CRITICAL first:
  1. Write a failing test that demonstrates it. If you cannot, the finding is
     not specific enough yet.
  2. Make the smallest change that passes it.
  3. Re-run the full baseline from Step 1.
  4. Commit, one defect per commit, message explaining the failure mode rather
     than the diff.

If a fix requires changing more than about 30 lines outside tests, stop and
report the design problem instead of performing surgery.

SCOPE — WHAT NOT TO DO
  - no new features, endpoints, pages or commands
  - no refactoring for its own sake, no renaming, no reformatting
  - no dependency upgrades unless one IS the defect
  - do not touch `app/services` logic without a failing test proving it wrong
  - do not weaken a test to make it pass; if a test is wrong, say why
  - do not fix LOW findings; list them

Anything you want to do that is out of scope becomes a line in the report.

REPORT
  1. Baseline — the Step 1 numbers, before you changed anything
  2. Findings table — severity, one-line summary, file:line, reproduced yes/no
  3. Per defect fixed — the failure mode, the trigger, the fix, the test
  4. Not fixed, and why — out of scope, needs a decision, or not reproducible
  5. Final verification — the same Step 1 numbers, after
  6. Anything that needs a human: a decision, a credential, network access

If you find nothing CRITICAL or HIGH, say that plainly. A clean audit reported
honestly is worth more than a list of nits, and this project has been audited
before — a long list of new CRITICALs more likely means you misread something
than that eight phases of tests all missed it.
````

---

## Design notes

**Why the ordering.** The audit sections are ranked by where defects have
actually come from in this repository, not by textbook categories. Every serious
bug in Phase 8 came from section 1 (environment-specific) — undeclared
dependencies, a version pin nothing ran against, `localhost` resolving to IPv6.
A generic "review code quality" instruction would have found none of them, and
would have produced a page of style opinions instead.

**Why the baseline is mandatory and numeric.** Without it an agent cannot
distinguish a bug it found from a bug it caused, and will report both as
findings. The exact expected numbers (1072/2, 56, 3) make a regression obvious
instead of arguable. Update them when they change.

**Why "suspicion" is a named category.** The common failure mode of audit
prompts is confident speculation — "this could race", "this might leak" — which
costs more to disprove than to write. Giving unreproducible observations their
own label lets the agent record them without licensing a fix.

**Why a failing test comes before the fix.** It forces the finding to be
specific, and it leaves evidence the bug existed. A fix with no test is
indistinguishable from a change of mind.

**Why the rule is stated as unbreakable, with an escape hatch.** The
architectural rule is the product. But an instruction with no legitimate way to
dissent invites quiet violation, so the prompt says: if you think the rule is
the bug, say so and stop.

**Why the 30-line limit.** It converts a scope decision into a report line,
which is where it belongs. An agent halfway through a 300-line refactor will
finish it; one that stops at 30 lines asks first.

**Why the closing paragraph.** Audit prompts reward finding things, so agents
find things. Saying that a clean result is an acceptable answer — and that a
pile of new CRITICALs in a well-tested codebase probably means misreading —
reduces invented severity.

**What to update when the project changes:** the baseline numbers in Step 1,
the commands if entry points move, and section 1's examples as new
environment-specific failure classes appear.

**Known limitations.** It assumes Docker, Postgres and Redis are available; a
machine without them will skip the checks that find the most. It will not find
UX or product problems — it is aimed at defects. And it deliberately will not
improve code that works, so it is the wrong tool for reducing technical debt.
