# Local-model evaluation (and the fine-tune we did not need)

FinMentor's local model writes prose. It never computes a figure — the engine
does that before the model is called, and `app/ai/safety.py` checks every
number on the way out. So the only things worth measuring here are the ways a
small model can be *wrong about verified numbers* rather than wrong *in* them.

## What is measured

`probes.py` grades one answer on seven checks, each a defect seen in a live run:

| check | the defect it catches |
|---|---|
| `verdict` | judging a bounded score the opposite way to the engine — "17.5/20 debt load, a bit high" |
| `sides` | a correct figure on the wrong side — "1.82 months after" when 1.82 was the before |
| `grounded` | a number that traces to nothing in the context (`safety.ungrounded_numbers`) |
| `no_advice` | a surviving buy/sell instruction (`safety._BUY_SELL_RE`) |
| `on_topic` | answering something else, or naming an asset when asked what to buy |
| `warm` | a data dump instead of a reply |
| `consistent` | contradicting a plain fact — "you're not onboarded yet" over a snapshot that says otherwise |

`make_probes.py` builds 22 probes by running the **real** engine and the
**real** context builders over four synthetic people (`demo`, `comfortable`,
`debt_heavy`, `no_goals`). Nothing is a hand-written fixture, so a change to
the engine's output shape changes the probes with it. The four people exist so
that a model which calls everything "a bit low" is visibly right about one and
wrong about three.

## Running it

```bash
# one model, verbose
python scripts/ft/compare_models.py llama3.2:3b --verbose

# the gate: several models, three passes each (temperature is 0.3, so a
# single pass is a sample, not a measurement)
python scripts/ft/compare_models.py llama3.2:3b qwen2.5:3b --repeat 3
```

Answers go through `synthesizer.explain` / `synthesizer.chat`, so what is
scored is what a user would actually receive — safety downgrades included. A
downgraded answer shows up as `warm` failing, because the user got a table.

## The gate decision — 2026-09-09

Bar: a stock model clearing ~9/10. Three passes each, 22 probes:

| model | runs | mean | verdict | sides | grounded | no_advice | sec |
|---|---|---|---|---|---|---|---|
| **llama3.2:3b** | 19, 20, 21 | **20.0/22 (91%)** | 37/39 | 15/15 | 66/66 | 66/66 | 2.6 |
| qwen2.5:3b | 18, 21, 19 | 19.3/22 (88%) | 38/39 | 15/15 | 66/66 | 66/66 | 2.5 |

`qwen2.5:7b` could not be tested: `ollama pull` failed twice from this machine
(DNS, then a blocked socket to Cloudflare R2). Worth retrying elsewhere.

**Decision: no fine-tune.** Stock `llama3.2:3b` clears the bar, and — more to
the point — the three defects a fine-tune was meant to fix are gone for a
cheaper reason. They were fixed by changing what the model is *shown*:

- the chat snapshot now carries the engine's own verdict next to each
  component and no raw score, so there is no bounded score left to misjudge;
- what-if and purchase contexts are rendered as a labelled `BEFORE … | AFTER …`
  block ahead of the JSON, so sides are copied rather than inferred;
- `safety.numbers_in_context` now grounds on magnitude, so a negative figure
  ("savings after: $-36,000,000") no longer flags the deterministic rendering
  as invented.

Fine-tuning is a standing obligation: every base-model bump is a retrain. It is
not worth taking on for defects that a better prompt payload already removed.

## What is left, and what a fine-tune would buy

Across six runs the residue is small and two-shaped:

1. **An occasional verdict slip** (~1 answer in 20) — usually the model adding
   its own adjective next to a component it did not need to characterise.
2. **A safety downgrade** (0-3 per run) — the model invents a figure, safety
   discards its text and renders the verified context, and the user gets a
   correct table instead of a warm reply.

A fine-tune on ~600-1000 `context+question -> ideal answer` pairs would most
plausibly help (2), by teaching the model to stay inside the supplied figures.
If that becomes worth doing, the path is below; nothing about it is blocked.

## If a fine-tune is wanted later

The scaffolding this evaluation already provides:

- `make_probes.py::PEOPLE` — the synthetic profile generator to widen to 80-120
- `make_probes.py::health_context` / `chat_snapshot` — real contexts, and
  already the exact shapes `synthesizer` sends at inference
- `probes.py::score_answer` — the rubric, reusable as an automatic filter on
  teacher-drafted answers before human review

Then, on the 5070 Ti (12 GB):

```bash
pip install unsloth
python scripts/ft/train.py            # QLoRA r=16, seq 2048, 3 epochs, lr 2e-4
                                      # ~6-7 GB VRAM, ~15-25 min
```

Export and register with Ollama:

```bash
# merge to 16-bit, convert to GGUF Q4_K_M -> models/finmentor-3b.gguf
ollama create finmentor-3b -f models/Modelfile
LOCAL_LLM_MODEL=finmentor-3b python scripts/ft/compare_models.py finmentor-3b llama3.2:3b --repeat 3
```

The training data must serialise the user turn **exactly** as
`synthesizer.explain` / `.chat` do, or the model is tuned on a prompt shape it
will never see. `make_probes.py` is the place to borrow that from.

`data/ft/` and `models/*.gguf` are gitignored; the scripts and this report are
not.

## The rule does not move

A fine-tuned model would still not be trusted with a number. The engine
computes, the context is the only source of figures, `safety.enforce` runs on
100% of output, and a hallucinated figure is still discarded in favour of the
verified context. Fine-tuning could only ever change tone and consistency.
