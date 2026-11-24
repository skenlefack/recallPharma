"""Ajustement supervisé (SFT) d'un adaptateur LoRA sur les exemples du Copilot ; perte sur la seule réponse attendue.

Usage :
    uv run --group training python -m recallpharma.training.train_sft --recipe qwen2.5-0.5b-cpu \
        --data var/training/copilot-donnees-2026.11-1 --out var/models/adaptateurs/copilot-0.5b-sft

Le modèle de base n'est jamais modifié : on produit un adaptateur (quelques dizaines de Mo), servi tel quel par
vLLM (--enable-lora) ou par serve.py, et retiré en un geste si l'évaluation ou l'exploitation le désavoue.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
from typing import Any

import torch
from datasets import Dataset
from peft import LoraConfig
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from trl import SFTConfig, SFTTrainer

from recallpharma.training.chat import completion_text, prompt_text, tools_for
from recallpharma.training.recipe import load_recipe, provenance, read_jsonl, stratified


def load_base(recipe: dict[str, Any]) -> Any:
    kwargs: dict[str, Any] = {"dtype": torch.bfloat16 if recipe["bf16"] else torch.float32}
    if recipe["load_in_4bit"]:
        kwargs["quantization_config"] = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )
        kwargs["device_map"] = "auto"
    return AutoModelForCausalLM.from_pretrained(recipe["base_model"], **kwargs)


def lora_config(recipe: dict[str, Any]) -> LoraConfig:
    lo = recipe["lora"]
    return LoraConfig(
        r=lo["r"],
        lora_alpha=lo["alpha"],
        lora_dropout=lo["dropout"],
        target_modules=lo["target_modules"],
        task_type="CAUSAL_LM",
    )


def tokenize(tokenizer: Any, rows: list[dict[str, Any]], max_length: int) -> tuple[list[dict[str, Any]], int]:
    out, skipped = [], 0
    for r in rows:
        tools = tools_for(r)
        prompt = tokenizer(prompt_text(tokenizer, r["messages"], tools), add_special_tokens=False)["input_ids"]
        completion = tokenizer(completion_text(tokenizer, r["messages"], tools, r["target"]), add_special_tokens=False)[
            "input_ids"
        ]
        if len(prompt) + len(completion) > max_length:
            skipped += 1  # jamais tronqué : une invite coupée enseignerait une réponse sans ses données
            continue
        out.append({"input_ids": prompt + completion, "completion_mask": [0] * len(prompt) + [1] * len(completion)})
    return out, skipped


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--recipe", required=True)
    parser.add_argument("--data", type=pathlib.Path, required=True)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    args = parser.parse_args()
    recipe = load_recipe(args.recipe)
    sft = recipe["sft"]
    torch.manual_seed(recipe["seed"])

    tokenizer = AutoTokenizer.from_pretrained(recipe["base_model"])
    rows = stratified(read_jsonl(args.data / "sft.jsonl"), sft["max_examples"], recipe["seed"])
    examples, skipped = tokenize(tokenizer, rows, recipe["max_length"])
    lengths = sorted(len(e["input_ids"]) for e in examples)
    print(
        f"{len(examples)} exemples (écartés car trop longs : {skipped}) · longueur médiane {lengths[len(lengths) // 2]}"
    )

    config = SFTConfig(
        output_dir=str(args.out / "travail"),
        num_train_epochs=sft["epochs"],
        per_device_train_batch_size=sft["batch_size"],
        gradient_accumulation_steps=sft["grad_accum"],
        learning_rate=sft["learning_rate"],
        lr_scheduler_type="cosine",
        warmup_ratio=sft["warmup_ratio"],
        logging_steps=5,
        save_strategy="no",
        report_to=[],
        bf16=recipe["bf16"],
        gradient_checkpointing=recipe["gradient_checkpointing"],
        max_length=recipe["max_length"],
        completion_only_loss=True,
        seed=recipe["seed"],
        dataloader_pin_memory=torch.cuda.is_available(),
    )
    trainer = SFTTrainer(
        model=load_base(recipe),
        args=config,
        train_dataset=Dataset.from_list(examples),
        processing_class=tokenizer,
        peft_config=lora_config(recipe),
    )
    started = time.time()
    result = trainer.train()
    trainer.save_model(str(args.out))
    tokenizer.save_pretrained(str(args.out))
    losses = [h["loss"] for h in trainer.state.log_history if "loss" in h]
    card = {
        "stage": "sft",
        **provenance(recipe, args.data),
        "examples": len(examples),
        "skipped_too_long": skipped,
        "steps": result.global_step,
        "train_loss": result.training_loss,
        "loss_first": losses[0] if losses else None,
        "loss_last": losses[-1] if losses else None,
        "loss_curve": losses,
        "duration_s": round(time.time() - started),
        "device": "cuda" if torch.cuda.is_available() else f"cpu ({torch.get_num_threads()} fils)",
    }
    (args.out / "entrainement.json").write_text(json.dumps(card, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in card.items() if k != "loss_curve"}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
