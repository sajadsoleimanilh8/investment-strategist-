"""QLoRA fine-tune of Llama-3.2-3B-Instruct on data/ft/{train,val}.jsonl.

    python scripts/ft/train.py [--epochs 3] [--out outputs/finmentor-3b]

Standalone. Nothing under `app/` imports this, and this imports nothing from
`app/` — the running product talks to Ollama over HTTP and has no ML
dependency at all.

Two backends, same hyperparameters:

* **Unsloth**, if it is installed — faster and lighter, and what the brief
  specifies.
* **peft + trl + bitsandbytes** otherwise. This is the path that actually ran
  here: installing Unsloth would have downgraded `transformers`, `trl` and
  `datasets` in a shared interpreter that other work depends on, and plain
  QLoRA fits a 3B on 12 GB comfortably. The maths is the same; Unsloth is a
  speed optimisation, not a different method.

The result is a LoRA adapter. `export.py` merges it and produces the GGUF that
Ollama loads.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

#: Unsloth's mirror either way: identical weights to Meta's repo but ungated,
#: so a run needs no Hugging Face licence acceptance or token.
BASE_MODEL = "unsloth/Llama-3.2-3B-Instruct"
FALLBACK_BASE = "unsloth/Llama-3.2-3B-Instruct"

#: Every attention and MLP projection, which is what makes a small-rank adapter
#: able to shift style without a large-rank one's memory cost.
TARGET_MODULES = ["q_proj", "k_proj", "v_proj", "o_proj",
                  "gate_proj", "up_proj", "down_proj"]


def load_rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def have_unsloth() -> bool:
    try:
        import unsloth  # noqa: F401
        return True
    except Exception:
        return False


def build_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="data/ft")
    parser.add_argument("--out", default="outputs/finmentor-3b")
    parser.add_argument("--base", default=None, help="override the base model id")
    parser.add_argument("--epochs", type=float, default=3)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--rank", type=int, default=16)
    parser.add_argument("--seq-len", type=int, default=2048)
    parser.add_argument("--batch", type=int, default=2)
    parser.add_argument("--grad-accum", type=int, default=4)
    parser.add_argument("--eval-steps", type=int, default=50)
    parser.add_argument("--seed", type=int, default=20260909)
    return parser.parse_args()


def main() -> None:
    args = build_args()
    import torch
    from datasets import Dataset
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    data = Path(args.data)
    train_rows = load_rows(data / "train.jsonl")
    val_rows = load_rows(data / "val.jsonl")
    print(f"train {len(train_rows)}  val {len(val_rows)}")

    unsloth = have_unsloth()
    base = args.base or (BASE_MODEL if unsloth else FALLBACK_BASE)
    print(f"backend: {'unsloth' if unsloth else 'peft+trl'}   base: {base}")

    if unsloth:
        from unsloth import FastLanguageModel

        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=base, max_seq_length=args.seq_len,
            load_in_4bit=True, dtype=None,
        )
        model = FastLanguageModel.get_peft_model(
            model, r=args.rank, lora_alpha=args.rank, lora_dropout=0.0,
            target_modules=TARGET_MODULES, use_gradient_checkpointing="unsloth",
            random_state=args.seed,
        )
    else:
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

        tokenizer = AutoTokenizer.from_pretrained(base)
        model = AutoModelForCausalLM.from_pretrained(
            base,
            quantization_config=BitsAndBytesConfig(
                load_in_4bit=True, bnb_4bit_quant_type="nf4",
                bnb_4bit_compute_dtype=torch.bfloat16,
                bnb_4bit_use_double_quant=True,
            ),
            dtype=torch.bfloat16, device_map={"": 0},
        )
        model.config.use_cache = False
        model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
        model = get_peft_model(model, LoraConfig(
            r=args.rank, lora_alpha=args.rank, lora_dropout=0.0, bias="none",
            task_type="CAUSAL_LM", target_modules=TARGET_MODULES,
        ))
        model.print_trainable_parameters()

    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    # The rows are conversational prompt/completion pairs. TRL applies the chat
    # template itself and — because the columns are split — masks the prompt, so
    # loss lands on the assistant turn alone.
    train_ds = Dataset.from_list(train_rows)
    val_ds = Dataset.from_list(val_rows)
    print(f"columns: {train_ds.column_names}")
    print("sample completion: " + train_ds[0]["completion"][0]["content"][:200])

    from trl import SFTConfig, SFTTrainer

    config = SFTConfig(
        output_dir=args.out,
        per_device_train_batch_size=args.batch,
        per_device_eval_batch_size=args.batch,
        gradient_accumulation_steps=args.grad_accum,
        num_train_epochs=args.epochs,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=0.05,
        logging_steps=10,
        eval_strategy="steps",
        eval_steps=args.eval_steps,
        save_strategy="steps",
        save_steps=args.eval_steps,
        save_total_limit=2,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        bf16=True,
        max_length=args.seq_len,
        # Packing concatenates examples to fill the context window. With a
        # prompt this much larger than its completion it buys throughput and
        # costs correctness — the first run packed, trained on the whole
        # sequence, and produced a model that emitted JSON contexts instead of
        # replies. Off, with the prompt masked, is the only correct setting here.
        packing=False,
        completion_only_loss=True,
        gradient_checkpointing=True,
        report_to=[],
        seed=args.seed,
    )

    trainer = SFTTrainer(
        model=model, args=config, train_dataset=train_ds, eval_dataset=val_ds,
        processing_class=tokenizer,
    )

    started = time.perf_counter()
    torch.cuda.reset_peak_memory_stats()
    result = trainer.train()
    elapsed = time.perf_counter() - started
    peak_gb = torch.cuda.max_memory_allocated() / 1024 ** 3

    print(f"\ntrained in {elapsed / 60:.1f} min, peak VRAM {peak_gb:.1f} GB")
    print(f"final train loss {result.training_loss:.4f}")
    print("eval:", trainer.evaluate())

    adapter = Path(args.out) / "adapter"
    trainer.model.save_pretrained(adapter)
    tokenizer.save_pretrained(adapter)
    print(f"adapter -> {adapter}")

    (Path(args.out) / "run.json").write_text(json.dumps({
        "base": base, "backend": "unsloth" if unsloth else "peft+trl",
        "train_rows": len(train_rows), "val_rows": len(val_rows),
        "epochs": args.epochs, "lr": args.lr, "rank": args.rank,
        "minutes": round(elapsed / 60, 1), "peak_vram_gb": round(peak_gb, 1),
        "train_loss": result.training_loss,
    }, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
