"""Serveur d'évaluation compatible OpenAI (/v1/chat/completions) pour un modèle de base et, au besoin, un adaptateur.

Usage (évaluation hors ligne d'un candidat, sans GPU) :
    uv run --group training python -m recallpharma.training.serve --base var/models/Qwen2.5-0.5B-Instruct \
        [--adapter var/models/adaptateurs/copilot-0.5b-dpo] --port 8003
puis la passerelle avec RECALLPHARMA_LLM_BASE_URL=http://127.0.0.1:8003/v1.

En production, vLLM sert le même adaptateur sans fusion :
    vllm serve Qwen/Qwen2.5-7B-Instruct --enable-lora --lora-modules copilot=<adaptateur> \
        --enable-auto-tool-choice --tool-call-parser hermes
La mise en forme passe par chat.py, la même qu'à l'entraînement.
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from typing import Any

import torch
import uvicorn
from fastapi import FastAPI
from transformers import AutoModelForCausalLM, AutoTokenizer

from recallpharma.training.chat import parse_reply, prompt_text


def create_app(base: str, adapter: str | None) -> FastAPI:
    tokenizer = AutoTokenizer.from_pretrained(adapter or base)
    model = AutoModelForCausalLM.from_pretrained(base, dtype=torch.float32)
    label = base.rstrip("/\\").split("/")[-1].split("\\")[-1]
    if adapter:
        from peft import PeftModel

        model = PeftModel.from_pretrained(
            model, adapter
        ).merge_and_unload()  # fusion en mémoire : inférence plus rapide
        label += "+" + adapter.rstrip("/\\").split("/")[-1].split("\\")[-1]
    model.eval()
    lock = threading.Lock()  # un seul calcul à la fois : le processeur est déjà saturé par une génération
    app = FastAPI(title=f"Modèle d'évaluation ({label})")

    @app.post("/v1/chat/completions")
    def complete(body: dict[str, Any]) -> dict[str, Any]:
        text = prompt_text(tokenizer, body["messages"], body.get("tools"))
        inputs = tokenizer(text, return_tensors="pt", add_special_tokens=False)
        with lock, torch.inference_mode():
            output = model.generate(
                **inputs,
                max_new_tokens=int(body.get("max_tokens") or 300),
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id,
            )
        generated = output[0][inputs["input_ids"].shape[1] :]
        raw = tokenizer.decode(generated, skip_special_tokens=False)
        for end in (tokenizer.eos_token, "<|endoftext|>"):
            raw = raw.split(end)[0]  # <tool_call> peut être un jeton spécial : on ne coupe que les fins de tour
        message = parse_reply(raw)
        return {
            "id": f"eval-{time.time_ns()}",
            "model": label,
            "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": int(inputs["input_ids"].shape[1]), "completion_tokens": len(generated)},
        }

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "model": label}

    return app


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--adapter")
    parser.add_argument("--port", type=int, default=8003)
    args = parser.parse_args()
    uvicorn.run(create_app(args.base, args.adapter), host="127.0.0.1", port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
