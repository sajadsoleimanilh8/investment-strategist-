"""Aggregate compare_models.py reports into one comparable table.

    python scripts/ft/scorecard.py REPORT.json [REPORT.json ...]
    python scripts/ft/scorecard.py "marked=a.json,b.json" "unmarked=c.json"

`compare_models.py` prints one line per run. That is the right view while a run
is in progress and the wrong one for a decision: with temperature at 0.3 a
single run moves by ±2 on its own, so a model has to be judged on the mean
across runs, with the spread shown next to it.

Every column is the same one the README's scorecard uses, so a new model's row
can be pasted in beside the old ones without re-deriving anything.
"""
from __future__ import annotations

import argparse
import collections
import json
import statistics
from pathlib import Path

#: Column -> the summary key it reads, and how many probes that check can fail.
#: `verdict` and `sides` only apply to the probes that carry a verdict or a
#: before/after pair, which is why their denominators are smaller than 22.
COLUMNS = ("verdict", "sides", "grounded", "no_advice", "on_topic", "warm")


def ratio(value: str) -> tuple[int, int]:
    """"13/13" -> (13, 13)."""
    passed, _, total = str(value).partition("/")
    return int(passed), int(total)


def load(groups: list[str]) -> dict[str, list[dict]]:
    """Every run's summary, keyed by model *and* the condition it ran under.

    Reports label runs "llama3.2:3b #2"; the model is the part before the `#`.
    A bare path is its own condition. `label=a.json,b.json` pools several
    reports under one label.

    The condition is not optional. Merging by model name alone once pooled
    marked and unmarked prompt runs into a single "11 runs" row — a number that
    describes no configuration anyone actually runs.
    """
    by_row: dict[str, list[dict]] = collections.defaultdict(list)
    for group in groups:
        label, _, paths = group.rpartition("=")
        for path in paths.split(","):
            condition = label or Path(path).stem.removeprefix("probe_")
            report = json.loads(Path(path).read_text(encoding="utf-8"))
            for run_label, result in report.items():
                model = run_label.split(" #")[0]
                by_row[f"{model} [{condition}]"].append(result["summary"])
    return by_row


def summarise(runs: list[dict]) -> dict:
    cleans = [ratio(run["clean_answers"])[0] for run in runs]
    probes = ratio(runs[0]["clean_answers"])[1]
    out = {
        "runs": len(runs),
        "clean": cleans,
        "probes": probes,
        "mean": statistics.mean(cleans),
        "spread": (min(cleans), max(cleans)),
        "downgrades": statistics.mean(run["safety_downgrades"] for run in runs),
        "seconds": statistics.mean(run["avg_seconds"] for run in runs),
        "words": statistics.mean(run["avg_words"] for run in runs),
    }
    for column in COLUMNS:
        passed = sum(ratio(run[column])[0] for run in runs)
        total = sum(ratio(run[column])[1] for run in runs)
        out[column] = (passed, total)
    return out


def render(by_model: dict[str, list[dict]]) -> str:
    rows = {model: summarise(runs) for model, runs in by_model.items()}
    order = sorted(rows, key=lambda model: -rows[model]["mean"])

    header = ("| model | runs | mean | spread | verdict | sides | grounded | "
              "no_advice | downgrades/run | sec | words |")
    lines = [header, "|" + "---|" * 11]
    for model in order:
        s = rows[model]
        cell = lambda col: f"{s[col][0]}/{s[col][1]}"     # noqa: E731
        lines.append(
            f"| {model} | {s['runs']} | **{s['mean']:.2f}/{s['probes']}** "
            f"({s['mean'] / s['probes'] * 100:.0f}%) | {s['spread'][0]}–{s['spread'][1]} "
            f"| {cell('verdict')} | {cell('sides')} | {cell('grounded')} "
            f"| {cell('no_advice')} | {s['downgrades']:.2f} "
            f"| {s['seconds']:.1f} | {s['words']:.0f} |"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", nargs="+")
    args = parser.parse_args()
    print(render(load(args.reports)))


if __name__ == "__main__":
    main()
