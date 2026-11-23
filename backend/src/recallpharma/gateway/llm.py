"""Client du modèle : interface compatible OpenAI (/v1/chat/completions), servie par vLLM en production et par
Ollama en développement. Le modèle propose des appels d'outils et rédige ; il n'exécute rien."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx


class ModelUnavailable(Exception):
    """Fournisseur injoignable, en erreur ou hors délai : le Copilot passe en mode dégradé (ENF-DIS-03)."""


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]
    invalid: str | None = None  # arguments illisibles : l'erreur est renvoyée au modèle, rien n'est exécuté


@dataclass(frozen=True, slots=True)
class Reply:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0


class ChatModel(Protocol):
    model_id: str

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        json_mode: bool = False,
        max_tokens: int = 300,
    ) -> Reply: ...


def _parse_arguments(raw: Any) -> tuple[dict[str, Any], str | None]:
    if isinstance(raw, dict):
        return raw, None
    try:
        value = json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}, "arguments JSON illisibles"
    return (value, None) if isinstance(value, dict) else ({}, "arguments JSON non objet")


class OpenAICompatibleModel:
    def __init__(self, base_url: str, model: str, *, api_key: str | None = None, timeout: float = 60.0) -> None:
        self.model_id = model
        headers = {"authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.Client(base_url=base_url.rstrip("/"), headers=headers, timeout=timeout)

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        json_mode: bool = False,
        max_tokens: int = 300,
    ) -> Reply:
        body: dict[str, Any] = {
            "model": self.model_id,
            "messages": messages,
            "temperature": 0,
            "max_tokens": max_tokens,
        }
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        try:
            res = self._client.post("/chat/completions", json=body)
            res.raise_for_status()
            data = res.json()
            message = data["choices"][0]["message"]
        except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
            raise ModelUnavailable(str(exc)) from exc
        calls = []
        for i, c in enumerate(message.get("tool_calls") or []):
            args, invalid = _parse_arguments(c.get("function", {}).get("arguments"))
            calls.append(ToolCall(c.get("id") or f"appel-{i}", c.get("function", {}).get("name", ""), args, invalid))
        usage = data.get("usage") or {}
        return Reply(
            content=message.get("content") or "",
            tool_calls=calls,
            tokens_in=int(usage.get("prompt_tokens", 0)),
            tokens_out=int(usage.get("completion_tokens", 0)),
        )
