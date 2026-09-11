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

## The fine-tune — built, evaluated, not shipped (2026-09-10)

The gate above said a fine-tune was not needed. It was built anyway, on
request, and the result is worth keeping on record: **stock still wins.**

| model | runs | mean | verdict | sides | grounded | no_advice | downgrades | sec |
|---|---|---|---|---|---|---|---|---|
| **llama3.2:3b (stock)** | 22, 22, 19 | **21.0/22 (95%)** | 39/39 | 15/15 | 66/66 | 66/66 | 0.3/run | 2.6 |
| finmentor-3b (run 2) | 17, 18, 18 | 17.7/22 (80%) | 38/39 | 15/15 | 66/66 | 66/66 | 3.7/run | 2.6 |

`LOCAL_LLM_MODEL` stays `llama3.2:3b`.

**Dataset:** 584 pairs from 40 synthetic people across 8 buckets, 522 train /
62 val, stratified by task and bucket. 99.8% of composed answers passed the
seven-check grader and `safety.enforce`; the rest were dropped. Answers average
47 words against ~1180-character prompts.

**Training:** QLoRA r=16 on `unsloth/Llama-3.2-3B-Instruct`, 3 epochs, lr 2e-4
cosine, bf16, on an RTX 5070 Ti (12 GB). **15.7 min, peak 4.8 GB VRAM**, eval
loss 0.0497, token accuracy 97.3%. Backend was peft+trl+bitsandbytes rather
than Unsloth — installing Unsloth would have downgraded `transformers`, `trl`
and `datasets` in a shared interpreter, and plain QLoRA fits a 3B on 12 GB with
room to spare. Same method; Unsloth is a speed optimisation.

### Run 1 was garbage, and why

The first run trained with `packing=True` and no prompt masking. These prompts
are ~1180 characters of JSON against a 47-word answer, so the loss was
dominated by the context — and the model learned to **emit JSON contexts**
instead of replying to them:

```
Here is where they stand:
{"onboarded": false, "health_score": 0.0, "components": [{"name": ...
```

19 of 22 answers were discarded by the safety layer. The fix is
`packing=False` + `completion_only_loss=True`, with the dataset emitted as
`prompt`/`completion` columns so TRL masks the prompt. Eval loss went 0.218 →
0.0497 and clean answers 7/22 → 17.7/22. `tests/unit/test_ft_dataset.py` now
pins the column split so this cannot silently regress.

### Why run 2 still lost

Tone and grounding are genuinely good — it copies verdict words (38/39), keeps
before/after sides (15/15), invents no numbers, gives no advice:

> "Sure — here's what you should focus on first. Your savings rate is Weak at
> -0.15. Your emergency fund is Weak at 0.07 months of essential expenses.
> Your goal progress is not available yet…"

What it lost is **task separation**. With 522 highly templated rows and eval
loss at 0.05, it memorised the shapes and then applied the *chat* shape to the
*explain* path — answering "why is my financial health score what it is?" with
a verdict list that never says the word "score", failing that probe 3/3. It
also drifted to "you're not onboarded" on 2 chat probes over snapshots saying
otherwise. Both are over-fitting to a composer that is too regular.

If this is picked up again, the two things to change are: more lexical and
structural variety per task (the composer has 3-4 frames per slot; it needs
more), and fewer epochs or a lower rank to stop it memorising. A teacher model
larger than 3B would help most, and cannot be pulled on this machine.

## qwen2.5:7b — measured, not adopted (2026-09-11)

Evaluation only; `LOCAL_LLM_MODEL` stays `llama3.2:3b`. Same 22 probes, three
runs, on the current (task-marked) prompts — the configuration that is live.
Aggregated with `scorecard.py`, which keeps rows from different prompt versions
apart:

| model | runs | mean | spread | verdict | sides | grounded | no_advice | downgrades/run | sec | words |
|---|---|---|---|---|---|---|---|---|---|---|
| qwen2.5:7b [marked] | 3 | **21.00/22** (95%) | 20–22 | 37/39 | 15/15 | 66/66 | 66/66 | 0.67 | 3.0 | 49 |
| llama3.2:3b [marked] | 4 | **20.00/22** (91%) | 19–21 | 51/52 | 20/20 | 88/88 | 88/88 | 1.25 | 2.6 | 59 |
| llama3.2:3b [unmarked, 2026-09-10] | 3 | 21.00/22 (95%) | 19–22 | 39/39 | 15/15 | 66/66 | 66/66 | 0.33 | 2.6 | 55 |
| finmentor-3b [unmarked, 2026-09-10] | 3 | 17.67/22 (80%) | 17–18 | 38/39 | 15/15 | 66/66 | 66/66 | 3.67 | 2.6 | 52 |

The honest reading: **the 7B is one probe better on the mean, and that is
inside the noise.** Single runs of the same model at temperature 0.3 swing by
±2, and the 3B's own two marked/unmarked samples (20.0 and 21.0) differ by as
much as the 7B beats it by. Both invent nothing and advise nothing on every
answer across every run.

Where they differ is in the detail. The 7B is terser (49 words vs 59) and
downgraded about half as often (0.67 vs 1.25 per run) — fewer invented figures
for safety to catch. Its three misses were two verdict slips and one data dump,
all on chat probes (`chat_focus:demo` twice, `chat_what_should_i_buy` once),
not the explain path.

**Latency is not the objection it was expected to be.** 3.0 s against 2.6 s,
about 15% slower on the RTX 5070 Ti — not the doubling predicted before it was
measured. Memory is the real cost: 4.7 GB on disk against 2.0 GB, which matters
for a GPU that may be shared with anything else.

Getting it here was its own problem. `ollama pull` failed twice earlier (DNS,
then a blocked socket), and this time the parallel downloader stalled at 0% for
17 minutes while a single connection trickled at 0.1 MB/s. Throughput turned out
to be bursty rather than blocked: 36 MB/s for a minute, then near-zero, with a
server restart in between that the pull resumed from at 53%. Ollama's chunk
tracker files are flushed only periodically, so a monitor reading them reports
a stall while the download is running; read Ollama's own progress line instead.

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
