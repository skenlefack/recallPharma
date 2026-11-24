"""Mise en forme des exemples pour le gabarit de conversation du modèle de base, à l'identique en entraînement et en
service : un écart de gabarit entre les deux ruinerait l'ajustement sans que l'évaluation hors ligne le voie.

Les exemples sont stockés au format OpenAI (celui des invites du service) ; seul ce module connaît le gabarit, et il
le délègue au tokenizer du modèle (apply_chat_template), jamais à une mise en forme écrite à la main.
"""

from __future__ import annotations

import json
import re
from typing import Any, Protocol

from recallpharma.gateway.tools import TOOL_SPECS

_TOOL_CALL = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.S)


class ChatTemplate(Protocol):
    eos_token: str

    def apply_chat_template(self, conversation: Any, **kwargs: Any) -> Any: ...


def _arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def to_hf(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Messages OpenAI → messages du gabarit Hugging Face (arguments d'appel en objet, pas en chaîne JSON)."""
    out = []
    for m in messages:
        m = dict(m)
        if m.get("tool_calls"):
            m["tool_calls"] = [
                {
                    "type": "function",
                    "function": {
                        "name": (c.get("function") or c)["name"],
                        "arguments": _arguments((c.get("function") or c).get("arguments")),
                    },
                }
                for c in m["tool_calls"]
            ]
        out.append(m)
    return out


def target_message(target: dict[str, Any]) -> dict[str, Any]:
    msg: dict[str, Any] = {"role": "assistant", "content": target.get("content") or ""}
    if target.get("tool_calls"):
        msg["tool_calls"] = [
            {"type": "function", "function": {"name": c["name"], "arguments": c["arguments"]}}
            for c in target["tool_calls"]
        ]
    return msg


def tools_for(example: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Les exemples de planification portent les outils du service ; ceux de rédaction, aucun."""
    return TOOL_SPECS if example.get("tools") else None


def prompt_text(tokenizer: ChatTemplate, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None) -> str:
    return str(tokenizer.apply_chat_template(to_hf(messages), tools=tools, add_generation_prompt=True, tokenize=False))


def completion_text(
    tokenizer: ChatTemplate, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None, target: dict[str, Any]
) -> str:
    """Suite attendue de l'invite, jusqu'au jeton de fin de tour inclus (rien après)."""
    prompt = prompt_text(tokenizer, messages, tools)
    full = str(tokenizer.apply_chat_template([*to_hf(messages), target_message(target)], tools=tools, tokenize=False))
    if not full.startswith(prompt):
        raise ValueError("gabarit non préfixe : l'invite seule ne prolonge pas la conversation complète")
    completion = full[len(prompt) :]
    end = completion.rfind(tokenizer.eos_token)
    return completion[: end + len(tokenizer.eos_token)] if end >= 0 else completion + tokenizer.eos_token


def parse_reply(text: str) -> dict[str, Any]:
    """Sortie brute du modèle → message OpenAI (contenu et appels d'outils au format <tool_call> du gabarit)."""
    calls = []
    for i, raw in enumerate(_TOOL_CALL.findall(text)):
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and "name" in value:
            calls.append(
                {
                    "id": f"appel-{i}",
                    "type": "function",
                    "function": {
                        "name": str(value["name"]),
                        "arguments": json.dumps(value.get("arguments") or {}, ensure_ascii=False),
                    },
                }
            )
    content = _TOOL_CALL.sub("", text).strip()
    return {"role": "assistant", "content": content, "tool_calls": calls}
