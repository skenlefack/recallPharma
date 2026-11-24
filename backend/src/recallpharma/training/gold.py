"""Modèle « de référence » : joue un scénario à travers le vrai parcours du Copilot (orchestrateur, outils, contrôle).

Il implémente l'interface ChatModel de la passerelle et ne lit que ce qu'un modèle lirait : les messages. Les
invites capturées sont donc exactement celles du service, et la rédaction de référence passe le même contrôle.
"""

from __future__ import annotations

import json
import re
from typing import Any

from recallpharma.gateway.llm import Reply, ToolCall
from recallpharma.training.scenarios import (
    FIRST_ROW,
    LIST_EN,
    LIST_FR,
    LIST_ONE_EN,
    LIST_ONE_FR,
    REFINE_EN,
    REFINE_FR,
    Call,
    Scenario,
)

_DATA = re.compile(r"<donnees_outil>\n(.*)\n</donnees_outil>", re.S)
_RECORD = re.compile(r"^([^\s:]+) : (\{.*\})$", re.M)
_PLACEHOLDER = re.compile(r"\{(liste|ligne1|ligne2|delai|calcul|alerte)\}")


def tool_results(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for m in messages:
        if m["role"] == "tool":
            found = _DATA.search(m["content"])
            if found:
                out.append(json.loads(found.group(1)))
    return out


def records_in(messages: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    """Enregistrements présentés à la rédaction (bloc <enregistrements> de l'invite)."""
    text = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    return {rid: json.loads(body) for rid, body in _RECORD.findall(text)}


def slots(records: dict[str, dict[str, str]]) -> dict[str, str]:
    ids = list(records)
    rows = [i for i in ids if i.startswith("amm-") and "#" not in i]
    found: dict[str, str] = {}
    lists = [i for i in ids if i.startswith("liste")]
    if lists:
        found["liste"] = lists[-1]
    for n, rid in enumerate(rows[:2], start=1):
        found[f"ligne{n}"] = rid
    for key, prefix in (("delai", "#delai"), ("calcul", "calcul"), ("alerte", "alr-")):
        match = next((i for i in ids if prefix in i), None)
        if match:
            found[key] = match
    return found


def fill(template: str, records: dict[str, dict[str, str]]) -> str | None:
    """Remplit une rédaction ; None si une référence manque ou désigne un champ absent."""
    found = slots(records)
    if any(name not in found for name in _PLACEHOLDER.findall(template)):
        return None
    text = _PLACEHOLDER.sub(lambda m: found[m.group(1)], template)
    for rid, fld in re.findall(r"\[\[([^\[\]:]+):([^\[\]]+)\]\]", text):
        if fld not in records.get(rid, {}):
            return None
    return text


def choose_draft(sc: Scenario, records: dict[str, dict[str, str]]) -> str | None:
    """Première rédaction applicable ; pour un affinage vide, la rédaction « aucun » ; pour un délai absent, idem."""
    total = next((r.get("total") for rid, r in records.items() if rid.startswith("liste")), None)
    candidates = list(sc.drafts)
    if total == "1" and sc.drafts in (LIST_FR, LIST_EN, REFINE_FR, REFINE_EN):
        candidates = list(LIST_ONE_EN if sc.language == "en" else LIST_ONE_FR)
    if sc.intent == "affinage":
        empty = [t for t in candidates if t.startswith(("Aucun", "No product"))]
        candidates = empty if total == "0" else [t for t in candidates if t not in empty]
    if sc.intent == "delai":
        absent = [t for t in candidates if "ne donne pas" in t or "gives no" in t]
        has_delay = any("#delai" in rid for rid in records)
        candidates = [t for t in candidates if t not in absent] if has_delay else absent
    for template in candidates:
        text = fill(template, records)
        if text:
            return text
    return None


class GoldModel:
    model_id = "reference-scenarisee"

    def __init__(self, scenario: Scenario) -> None:
        self.sc = scenario

    def _resolve(self, call: Call, results: list[dict[str, Any]]) -> ToolCall | None:
        args = dict(call.arguments)
        for k, v in args.items():
            if v == FIRST_ROW:
                rows = next((r.get("lignes") for r in reversed(results) if r.get("lignes")), None)
                if not rows:
                    return None  # rien à lire : le modèle s'arrête, le parcours s'abstient
                args[k] = rows[0]["id"]
        return ToolCall(f"appel-{call.name}", call.name, args)

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        json_mode: bool = False,
        max_tokens: int = 300,
    ) -> Reply:
        if json_mode:
            draft = choose_draft(self.sc, records_in(messages))
            return Reply(json.dumps({"texte": draft or ""}, ensure_ascii=False))
        last_user = max(i for i, m in enumerate(messages) if m["role"] == "user")
        done = sum(1 for m in messages[last_user:] if m["role"] == "assistant" and m.get("tool_calls"))
        if done >= len(self.sc.rounds):
            return Reply("")
        results = tool_results(messages[last_user:])
        calls = [self._resolve(c, results) for c in self.sc.rounds[done]]
        return Reply("", [c for c in calls if c is not None])
