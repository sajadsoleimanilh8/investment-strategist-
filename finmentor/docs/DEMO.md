# Demo runbook

A walkthrough of FinMentor on both surfaces. Roughly eight minutes on the web,
five on Telegram. Everything below works with no internet: no market API, no
Ollama, no remote LLM.

## Before you start

```bash
docker compose up -d          # web :5173, API :8000, db, redis
```

From a clean checkout that is the whole setup — the schema migrates and the
demo data seeds on boot. Wait for all four containers to report healthy
(`docker compose ps`), then open <http://localhost:5173>.

For the Telegram half you also need a bot token from @BotFather in `.env`, and
`python -m app.bot.main` running.

**The one sentence to open with.** FinMentor is not a chatbot with a finance
theme. A deterministic engine computes every number first; the model only ever
puts those numbers into sentences. That ordering is the product, and the demo
is built to show it.

---

## Web

### 1. Signup and onboarding — 2 min

Sign up with any email and a password of ten characters or more. You land on
onboarding, not the dashboard, because there are no numbers yet.

Four steps: income, eight spending categories, current position, and one goal.
Use round numbers so the arithmetic is checkable out loud:

| field | value |
|---|---|
| Monthly income | 30,000,000 |
| Housing / food / transport | 8,000,000 / 5,000,000 / 2,000,000 |
| Bills / entertainment / shopping | 1,500,000 / 1,000,000 / 1,000,000 |
| Total savings | 45,000,000 |
| Debt, and the monthly payment | 12,000,000 / 1,500,000 |
| Emergency fund | 30,000,000 |
| Goal | Laptop, 60,000,000, 20,000,000 saved |

> Nothing is written until the last step. Abandoning halfway leaves no
> half-built profile.

### 2. The dashboard — 1 min

**Financial health: 62.3 / 100**, from five components out of 20 each.

Worth saying aloud: the score is not a model's opinion. Savings rate scores
20/20 because 33.3% clears the 25% target; emergency fund scores 6.1 because
1.8 months is short of six. The same inputs always give 62.3.

Then Financial DNA — the same components as words, so *Strong / Weak /
Moderate* rather than numbers.

### 3. A what-if — 1 min

**Simulate → "Extra saved each month: 5,000,000" → Run it.**

Before and after, side by side: saving goes 10,000,000 → 15,000,000, projected
savings 285,000,000 → 405,000,000, and the goal date pulls in by a month.

### 4. A purchase — 1 min

**"What it costs: 60,000,000" → Show me.**

Savings 45,000,000 → 0, emergency cover 1.8 → 0.9 months, health 62.3 → 59.2.

> The point to land: it does **not** say whether to buy it. It shows what
> happens and stops. The API sends no verdict and the page invents none —
> there is a test that greps the rendered output for verdict language.

### 5. Market — 1 min

**Market →** add a few symbols. Ranked by 7-day momentum, green and red deltas,
and a disclaimer on every payload.

No network is involved: prices come from seeded snapshots via the mock
provider, which is the same path a real provider outage takes.

### 6. Ask — 1 min

**Ask → "why is my health score what it is?"**

With no Ollama running, the answer is labelled *"the model was unavailable"* —
and still contains 62.3 and the real component breakdown.

> This is the best thirty seconds of the demo. The model is gone and the user
> still gets every number, because the numbers were never the model's to
> produce. Start Ollama and ask again: the same figures, in warmer prose.

### 7. Learn — 1 min

Twelve curated lessons, each with an explanation, an example, the mistake
beginners make, and a one-question check. Written by people, not generated —
so they are accurate, and the model may rephrase one but never invent one.

---

## Telegram

Same engine, same pipeline, different delivery. `/start` and walk through:

| command | what to point at |
|---|---|
| `/start` | onboarding conversation, same four steps |
| `/health` | 62.3/100 with bar charts, then the DNA |
| `/goals` | progress and a projected date per goal |
| `/simulate` `what if I save 5m more a month` | the deterministic table **first**, the prose second |
| *(then)* `60m` on "evaluate a purchase" | before/after, no verdict |
| `/market` | the same ranked watchlist |
| `/ask` `why is my score what it is` | with Ollama stopped: the verified figures |
| `/learn` | a topic and its quiz |

The bot never calls the API over HTTP — it imports the same pipeline functions
the web routes use, which is why adding web auth could not break it.

---

## If someone asks

**"How do you stop it hallucinating a number?"** Three layers. The engine
computes everything before the model is called; the model is handed a finished
context and told to use nothing else; and `app/ai/safety.py` checks every
figure in the output against that context, discarding the whole answer and
rendering the verified numbers if one does not trace back. A live 3B was caught
doing exactly that during development.

**"Does it give advice?"** No, by construction. The safety layer strips buy and
sell language from model output, and the decision simulator has no verdict to
strip — it reports consequences and stops.

**"What happens when the AI is down?"** You have already seen it. Prose is lost;
numbers are not.

**"Is the model fine-tuned?"** No. One was trained and evaluated — stock
`llama3.2:3b` beat it, so it was not shipped. The pipeline and the write-up are
in `scripts/ft/README.md`.

**"How much of this is tested?"** 1048 tests, 100% statement and branch
coverage on the deterministic engine, plus a browser flow and a gate that runs
the whole thing with every external service unreachable.
