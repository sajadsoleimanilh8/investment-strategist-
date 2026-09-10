"""Merge the LoRA adapter and register finmentor-3b with Ollama.

    python scripts/ft/export.py [--adapter outputs/finmentor-3b/adapter]

Two steps:

1. **Merge** the adapter into the base weights at bf16. QLoRA trains against a
   4-bit copy of the base, but the adapter itself is bf16, so the merge happens
   against the *unquantized* base — merging into the 4-bit copy would bake the
   quantization error permanently into the weights.
2. **Import** into Ollama. Since 0.28 Ollama reads a safetensors directory
   directly and quantizes on import (`-q q4_K_M`), so this needs no llama.cpp
   checkout and no separate GGUF step. `--gguf` still forces the old path if a
   GGUF file is wanted for its own sake.

The Modelfile carries the FinMentor system prompt so anything talking to the
model — including `ollama run` at a terminal — gets the same rules. The app
still sends its own; `app/ai/prompts.py` remains the single source of the text.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.ai.prompts import SYSTEM_PROMPT  # noqa: E402

BASE_MODEL = "unsloth/Llama-3.2-3B-Instruct"

MODELFILE = '''FROM {source}

PARAMETER temperature {temperature}
PARAMETER num_predict {num_predict}

SYSTEM """{system}"""
'''


def run(command: list[str]) -> None:
    print("+ " + " ".join(str(c) for c in command))
    subprocess.run(command, check=True)


def merge(adapter: Path, merged: Path, base: str) -> Path:
    """Adapter + unquantized base -> a plain safetensors model directory."""
    if (merged / "model.safetensors.index.json").exists() or \
            (merged / "model.safetensors").exists():
        print(f"merged weights already at {merged}")
        return merged

    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    print(f"loading {base} at bf16 (unquantized on purpose)")
    model = AutoModelForCausalLM.from_pretrained(base, dtype=torch.bfloat16,
                                                 device_map="cpu")
    model = PeftModel.from_pretrained(model, adapter)
    model = model.merge_and_unload()

    merged.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(merged, safe_serialization=True)
    AutoTokenizer.from_pretrained(adapter).save_pretrained(merged)
    print(f"merged -> {merged}")
    return merged


def to_gguf(merged: Path, gguf: Path, llama_cpp: Path) -> Path:
    """The old path, for when a GGUF file is wanted on its own."""
    converter = llama_cpp / "convert_hf_to_gguf.py"
    if not converter.exists():
        raise SystemExit(
            f"llama.cpp converter not found at {converter}.\n"
            "  git clone https://github.com/ggerganov/llama.cpp\n"
            "then re-run with --llama-cpp <path>, or drop --gguf and let Ollama "
            "import the safetensors directly."
        )
    gguf.parent.mkdir(parents=True, exist_ok=True)
    run([sys.executable, str(converter), str(merged),
         "--outfile", str(gguf), "--outtype", "f16"])
    return gguf


def write_modelfile(models: Path, source: Path, temperature: float,
                    num_predict: int) -> Path:
    models.mkdir(parents=True, exist_ok=True)
    path = models / "Modelfile"
    path.write_text(
        MODELFILE.format(
            source=source.resolve().as_posix(),
            temperature=temperature, num_predict=num_predict, system=SYSTEM_PROMPT,
        ),
        encoding="utf-8",
    )
    print(f"modelfile -> {path}")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adapter", default="outputs/finmentor-3b/adapter")
    parser.add_argument("--merged", default="outputs/finmentor-3b/merged")
    parser.add_argument("--models", default="models")
    parser.add_argument("--name", default="finmentor-3b")
    parser.add_argument("--base", default=BASE_MODEL)
    parser.add_argument("--quantize", default="q4_K_M",
                        help="Ollama import quantization; empty string keeps bf16")
    parser.add_argument("--gguf", action="store_true",
                        help="also convert to GGUF via llama.cpp")
    parser.add_argument("--llama-cpp", default="../llama.cpp")
    parser.add_argument("--temperature", type=float, default=0.3)
    parser.add_argument("--num-predict", type=int, default=400)
    parser.add_argument("--skip-ollama", action="store_true")
    args = parser.parse_args()

    merged = merge(Path(args.adapter), Path(args.merged), args.base)
    source = merged
    if args.gguf:
        source = to_gguf(merged, Path(args.models) / f"{args.name}.gguf",
                         Path(args.llama_cpp))

    modelfile = write_modelfile(Path(args.models), source, args.temperature,
                                args.num_predict)

    command = ["ollama", "create", args.name, "-f", str(modelfile)]
    if args.quantize:
        command += ["-q", args.quantize]

    if args.skip_ollama:
        print("\nskipping registration. To finish:\n  " + " ".join(command))
        return

    run(command)
    print(f"\n{args.name} registered. Evaluate it against stock:\n"
          f"  python scripts/ft/compare_models.py {args.name} llama3.2:3b --repeat 3")


if __name__ == "__main__":
    main()
