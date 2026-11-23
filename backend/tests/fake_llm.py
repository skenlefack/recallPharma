"""Faux serveur de modèle compatible OpenAI, déterministe, pour les parcours de bout en bout de l'écran Copilot.

uv run uvicorn tests.fake_llm:app --port 8002   puis   RECALLPHARMA_LLM_BASE_URL=http://127.0.0.1:8002/v1
Il passe par le vrai client HTTP de la passerelle ; il ne mesure rien de la qualité d'un modèle.
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI

app = FastAPI(title="Faux modèle (tests)")


def _message(content: str = "", tool_calls: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "id": "fake",
        "model": "faux-modele",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content, "tool_calls": tool_calls or []}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }


def _call(name: str, arguments: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"id": "c1", "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}]


@app.post("/v1/chat/completions")
def complete(body: dict[str, Any]) -> dict[str, Any]:
    messages = body["messages"]
    question = next(m["content"] for m in reversed(messages) if m["role"] == "user").casefold()
    if body.get("response_format"):
        return _message(json.dumps({"texte": "Le registre compte [[liste1:total]] produits pour cette recherche."}))
    if any(m["role"] == "tool" for m in messages):
        return _message()
    if "injectable" in question:
        return _message(tool_calls=_call("refine_result_set", {"form": "injectable"}))
    if "ivermectine" in question:
        return _message(tool_calls=_call("search_authorisations", {"substance": "ivermectine", "species": "bovins"}))
    return _message(tool_calls=_call("abstain", {"reason": "hors périmètre"}))
