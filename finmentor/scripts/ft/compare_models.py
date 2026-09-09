"""Run the probe set through several local models and score them.

The Part-B gate: if a stock model already clears the bar there is no reason to
fine-tune one, and every fine-tune is a retrain obligation on the next
base-model bump.

    python scripts/ft/compare_models.py llama3.2:3b qwen2.5:3b qwen2.5:7b

Answers go through the real `synthesizer` — same prompts, same safety layer —
so what is measured is what a user would actually receive, downgrades included.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("ENABLE_SCHEDULER", "false")
os.environ.setdefault("LOCAL_LLM_PROVIDER", "ollama")

from app.ai import synthesizer  # noqa: E402
from app.core.config import settings  # noqa: E402
from scripts.ft.make_probes import build_probes  # noqa: E402
from scripts.ft.probes import Probe, score_answer, summarise  # noqa: E402


def answer(probe: Probe) -> tuple[str, str, float]:
    """One probe through the real pipeline. Returns (text, source, seconds)."""
    started = time.perf_counter()
    if probe.task == "chat":
        result = synthesizer.chat(probe.question, probe.context, [])
    else:
        result = synthesizer.explain(
            probe.question, probe.context, market_context=probe.market_context
        )
    return result["text"], result["source"], time.perf_counter() - started


def run_model(model: str, probes: list[Probe], *, verbose: bool) -> dict:
    settings.local_llm_model = model
    scores, rows, latencies, lengths, downgrades = [], [], [], [], 0

    for probe in probes:
        try:
            text, source, seconds = answer(probe)
        except Exception as exc:                       # a model that will not load
            print(f"  !! {probe.key}: {type(exc).__name__}: {exc}")
            continue

        downgrades += source == "deterministic"
        score = score_answer(text, probe)
        scores.append(score)
        latencies.append(seconds)
        lengths.append(len(text.split("⚠")[0].split()))
        rows.append({
            "probe": probe.key, "question": probe.question, "source": source,
            "seconds": round(seconds, 2), "passed": score.passed,
            "failures": score.failures, "text": text.split("⚠")[0].strip(),
        })

        mark = "ok " if score.passed else "FAIL"
        print(f"  [{mark}] {probe.key:42} {seconds:5.1f}s  {source:13} "
              f"{'; '.join(score.failures)[:70]}")
        if verbose:
            print(f"        {rows[-1]['text'][:300]}")

    summary = summarise(scores)
    summary.update(
        model=model,
        avg_seconds=round(sum(latencies) / len(latencies), 1) if latencies else 0,
        avg_words=round(sum(lengths) / len(lengths)) if lengths else 0,
        safety_downgrades=downgrades,
    )
    return {"summary": summary, "rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("models", nargs="+", help="Ollama model tags to compare")
    parser.add_argument("--out", default="scripts/ft/probe_report.json")
    parser.add_argument("--verbose", action="store_true", help="print every answer")
    parser.add_argument("--repeat", type=int, default=1,
                        help="passes per model; temperature is non-zero, so one "
                             "pass is a sample, not a measurement")
    args = parser.parse_args()

    probes = build_probes()
    print(f"{len(probes)} probes, {len(args.models)} models\n")

    report = {}
    for model in args.models:
        for run in range(args.repeat):
            label = model if args.repeat == 1 else f"{model} #{run + 1}"
            print(f"=== {label} " + "=" * max(0, 60 - len(label)))
            report[label] = run_model(model, probes, verbose=args.verbose)
            print()

    print("=" * 78)
    header = ["model", "clean", "verdict", "sides", "grounded", "no_advice",
              "on_topic", "warm", "downgr", "sec", "words"]
    print(" | ".join(h.ljust(9) for h in header))
    for model, result in report.items():
        s = result["summary"]
        row = [model, s["clean_answers"], s["verdict"], s["sides"], s["grounded"],
               s["no_advice"], s["on_topic"], s["warm"],
               str(s["safety_downgrades"]), str(s["avg_seconds"]), str(s["avg_words"])]
        print(" | ".join(str(c).ljust(9) for c in row))

    Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False),
                              encoding="utf-8")
    print(f"\nfull transcripts -> {args.out}")


if __name__ == "__main__":
    main()
