"""Exemples tirés du journal du Copilot : seuls les échanges relus et jugés utiles entrent dans l'entraînement.

Règles de sélection (journal = données personnelles pseudonymisées, voir README) :
- réponse notée « utile » par son auteur, contrôle réussi, aucune suspicion d'injection ;
- une conversation effacée par l'utilisateur disparaît du journal, donc des jeux construits ensuite ;
- un échange signalé « erreur signalée » n'entre jamais : il va en revue qualité (ticket QUAL).
Une rédaction refusée au premier essai puis acceptée au second fournit une paire DPO réelle.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from recallpharma.db import models as m
from recallpharma.db.session import session_factory


def examples() -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    sft: list[dict[str, Any]] = []
    dpo: list[dict[str, Any]] = []
    stats = {"messages_utiles": 0, "ecartes_injection": 0, "signales_en_revue": 0}
    with session_factory()() as db:
        rows = db.execute(
            select(m.CopilotMessage, m.CopilotFeedback.rating)
            .join(m.CopilotFeedback, m.CopilotFeedback.message_id == m.CopilotMessage.id)
            .where(m.CopilotMessage.exchanges.is_not(None))
        ).all()
        for msg, rating in rows:
            if rating == "erreur signalée":
                stats["signales_en_revue"] += 1
                continue
            if rating != "utile":
                continue
            if msg.injection_suspected:
                stats["ecartes_injection"] += 1
                continue
            kind = (msg.payload or {}).get("answer", {}).get("kind")
            if kind not in ("answer", "abstention"):
                continue
            stats["messages_utiles"] += 1
            exchanges = msg.exchanges or []
            for i, ex in enumerate(exchanges):
                base = {
                    "id": f"journal-{msg.id}/{i}",
                    "scenario": f"journal-{msg.id}",
                    "intent": "journal",
                    "step": ex["step"],
                    "language": (msg.payload or {}).get("answer", {}).get("language", "fr"),
                    "messages": ex["messages"],
                    "tools": ex["step"] == "planification",
                    "source": "journal",
                }
                reply = {"content": ex["reply"]["content"], "tool_calls": ex["reply"]["tool_calls"]}
                passed = ex.get("check", {}).get("passed")
                if ex["step"] == "rédaction" and not passed:
                    nxt = exchanges[i + 1] if i + 1 < len(exchanges) else None
                    if nxt and nxt["step"] == "rédaction" and nxt.get("check", {}).get("passed"):
                        chosen = {"content": nxt["reply"]["content"], "tool_calls": []}
                        dpo.append({**base, "chosen": chosen, "rejected": reply})
                    continue
                sft.append({**base, "target": reply})
    return sft, dpo, stats


def dumps(rows: list[dict[str, Any]]) -> str:
    return "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)
