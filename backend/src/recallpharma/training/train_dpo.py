"""Optimisation par préférences (DPO) à partir de l'adaptateur SFT : la réponse conforme contre la faute observée.

Usage :
    uv run --group training python -m recallpharma.training.train_dpo --recipe qwen2.5-0.5b-cpu \
        --data var/training/copilot-donnees-2026.11-2 --sft var/models/adaptateurs/copilot-0.5b-sft \
        --out var/models/adaptateurs/copilot-0.5b-dpo

Fautes enseignées comme refusées : valeurs écrites en clair (RG-23), réponse de mémoire sans outil, recherche relancée
au lieu d'un affinage, abstention sur une AMM suspendue, appel répété, obéissance à une instruction cachée.
La référence de la DPO est le modèle SFT (et non le modèle de base) : on corrige des écarts, on ne repart pas de zéro.
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
from peft import PeftModel
from transformers import AutoTokenizer
from trl import DPOConfig, DPOTrainer

from recallpharma.training.chat import completion_text, prompt_text, tools_for
from recallpharma.training.recipe import load_recipe, provenance, read_jsonl, stratified
from recallpharma.training.train_sft import load_base


def pairs(tokenizer: Any, rows: list[dict[str, Any]], max_length: int) -> tuple[list[dict[str, str]], int]:
    out, skipped = [], 0
    for r in rows:
        tools = tools_for(r)
        prompt = prompt_text(tokenizer, r["messages"], tools)
        chosen = completion_text(tokenizer, r["messages"], tools, r["chosen"])
        rejected = completion_text(tokenizer, r["messages"], tools, r["rejected"])
        longest = max(len(tokenizer(prompt + c, add_special_tokens=False)["input_ids"]) for c in (chosen, rejected))
        if longest > max_length:
            skipped += 1
            continue
        out.append({"prompt": prompt, "chosen": chosen, "rejected": rejected})
    return out, skipped


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--recipe", required=True)
    parser.add_argument("--data", type=pathlib.Path, required=True)
    parser.add_argument("--sft", type=pathlib.Path, required=True, help="adaptateur SFT de départ")
    parser.add_argument("--out", type=pathlib.Path, required=True)
    args = parser.parse_args()
    recipe = load_recipe(args.recipe)
    dpo = recipe["dpo"]
    torch.manual_seed(recipe["seed"])

    tokenizer = AutoTokenizer.from_pretrained(str(args.sft))
    rows = stratified(read_jsonl(args.data / "dpo.jsonl"), dpo["max_pairs"], recipe["seed"])
    data, skipped = pairs(tokenizer, rows, recipe["max_length"])
    print(f"{len(data)} paires (écartées car trop longues : {skipped})")

    # Adaptateur SFT entraînable, sans ref_model : TRL en garde une copie figée (« ref ») comme référence.
    policy = PeftModel.from_pretrained(load_base(recipe), str(args.sft), is_trainable=True)
    config = DPOConfig(
        output_dir=str(args.out / "travail"),
        num_train_epochs=dpo["epochs"],
        per_device_train_batch_size=dpo["batch_size"],
        gradient_accumulation_steps=dpo["grad_accum"],
        learning_rate=dpo["learning_rate"],
        beta=dpo["beta"],
        lr_scheduler_type="cosine",
        logging_steps=2,
        save_strategy="no",
        report_to=[],
        bf16=recipe["bf16"],
        gradient_checkpointing=recipe["gradient_checkpointing"],
        max_length=recipe["max_length"],
        seed=recipe["seed"],
        dataloader_pin_memory=torch.cuda.is_available(),
    )
    trainer = DPOTrainer(
        model=policy,
        args=config,
        train_dataset=Dataset.from_list(data),
        processing_class=tokenizer,
    )
    started = time.time()
    result = trainer.train()
    trainer.save_model(str(args.out))
    tokenizer.save_pretrained(str(args.out))
    history = trainer.state.log_history
    card = {
        "stage": "dpo",
        "from_adapter": str(args.sft),
        **provenance(recipe, args.data),
        "pairs": len(data),
        "skipped_too_long": skipped,
        "steps": result.global_step,
        "train_loss": result.training_loss,
        "reward_accuracy_curve": [h.get("rewards/accuracies") for h in history if "rewards/accuracies" in h],
        "reward_margin_curve": [h.get("rewards/margins") for h in history if "rewards/margins" in h],
        "duration_s": round(time.time() - started),
        "device": "cuda" if torch.cuda.is_available() else f"cpu ({torch.get_num_threads()} fils)",
    }
    (args.out / "entrainement.json").write_text(json.dumps(card, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(card, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
