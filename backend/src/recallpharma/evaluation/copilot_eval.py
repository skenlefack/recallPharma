"""Rejoue le jeu de référence contre la passerelle et le modèle réels ; rapporte les métriques de CT-IA-01.

Usage (API et passerelle démarrées, modèle servi) :
    uv run python -m recallpharma.evaluation.copilot_eval [--repeat 3] [--gateway http://127.0.0.1:8001]
        [--reference src/recallpharma/evaluation/copilot-reference-300.json] [--limit 60]
        [--json rapport.json] [--label candidat]

Métriques : exactitude (bons enregistrements, bon type de réponse), abstention correcte, abstention à tort,
contrôle après génération réussi, mentions RG-26 présentes, bons outils appelés, exactitude sur les substances
réservées à l'évaluation (jamais vues à l'entraînement). Intervalles de confiance à 95 % (Wilson).
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from recallpharma.api.auth import mint_delegated

REFERENCE = pathlib.Path(__file__).with_name("copilot-reference.json")
METRICS = {
    "exact": "Exactitude",
    "abstain_ok": "Abstention correcte",
    "abstain_wrong": "Sans abstention à tort",
    "checked": "Contrôle réussi (sans repli)",
    "cited": "Contexte et mention (RG-26)",
    "tools": "Bons outils",
    "held_out": "Exactitude, substances inédites",
}


def wilson(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    z, p = 1.96, k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (max(0.0, centre - half), min(1.0, centre + half))


@dataclass
class Tally:
    ok: int = 0
    n: int = 0
    failures: list[str] = field(default_factory=list)

    def add(self, ok: bool, label: str) -> None:
        self.n += 1
        self.ok += ok
        if not ok:
            self.failures.append(label)

    def line(self, name: str) -> str:
        lo, hi = wilson(self.ok, self.n)
        rate = self.ok / self.n if self.n else 0
        return f"{name:<32} {self.ok:>3}/{self.n:<3} {rate:6.1%}  IC95 [{lo:.1%} ; {hi:.1%}]"


def ask(gateway: httpx.Client, case: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    body = {
        "question": case["question"],
        "jurisdiction": case.get("jurisdiction", "PA"),
        "jurisdiction_name": case.get("jurisdiction_name", "Pays A"),
        "as_of": "2027-09-07",
        "token": mint_delegated("cpt-03", None),
        **state,
    }
    out: dict[str, Any] = {}
    with gateway.stream("POST", "/v1/answer", json=body) as res:
        name = ""
        for line in res.iter_lines():
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                out[name] = json.loads(line[5:])
    return out


def select(cases: list[dict[str, Any]], limit: int | None) -> list[dict[str, Any]]:
    """Sous-échantillon stratifié et stable : toutes les intentions représentées, parents des affinages inclus."""
    if not limit or limit >= len(cases):
        return cases
    by_intent: dict[str, list[dict[str, Any]]] = {}
    for c in cases:  # les substances réservées forment leur propre strate : mesurées même en petit échantillon
        by_intent.setdefault(c.get("intent", "socle") + ("/inédite" if c.get("held_out") else ""), []).append(c)
    keep: set[str] = set()
    i = 0
    while len(keep) < limit and any(i < len(v) for v in by_intent.values()):
        for group in by_intent.values():
            if i < len(group) and len(keep) < limit:
                keep.add(group[i]["id"])
                if group[i].get("after"):
                    keep.add(group[i]["after"])
        i += 1
    return [c for c in cases if c["id"] in keep]


def state_after(case: dict[str, Any], trace: dict[str, Any], answer: dict[str, Any]) -> dict[str, Any]:
    """Comme l'API : le jeu précédent et la requête qui l'a produit, plus l'échange précédent."""
    query: dict[str, Any] = next(
        (c["arguments"] for c in reversed(trace["tool_calls"]) if c["tool"].endswith(("authorisations", "result_set"))),
        {},
    )
    return {
        "result_set_id": trace["result_set_id"],
        "result_set_query": query,
        "history": [{"question": case["question"], "answer": answer.get("text", "")}],
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # console Windows : rapport en UTF-8
    parser = argparse.ArgumentParser()
    parser.add_argument("--gateway", default="http://127.0.0.1:8001")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--reference", type=pathlib.Path, default=REFERENCE)
    parser.add_argument("--limit", type=int, help="sous-échantillon stratifié de N questions")
    parser.add_argument("--json", type=pathlib.Path, help="rapport détaillé, comparé par la promotion")
    parser.add_argument("--label", default="", help="nom du modèle évalué dans le rapport")
    args = parser.parse_args()
    reference = json.loads(args.reference.read_text(encoding="utf-8"))
    cases = select(reference["cases"], args.limit)
    gateway = httpx.Client(base_url=args.gateway, timeout=900)

    t = {k: Tally() for k in METRICS}
    durations: list[float] = []
    details: list[dict[str, Any]] = []
    trace: dict[str, Any] = {}
    for run in range(args.repeat):
        states: dict[str, dict[str, Any]] = {}
        for case in cases:
            label = f"{case['id']}#{run + 1}"
            t0 = time.monotonic()
            try:
                out = ask(gateway, case, states.get(case.get("after", ""), {}))
            except httpx.HTTPError as exc:
                out = {"error": {"message": str(exc)}}
            durations.append(time.monotonic() - t0)
            trace, answer, records = out.get("trace", {}), out.get("answer", {}), out.get("records", {})
            if trace.get("result_set_id"):
                states[case["id"]] = state_after(case, trace, answer)
            expect = case["expect"]
            got_ids = sorted(r["id"] for r in records.get("rows", []))
            ok = answer.get("kind") in (("answer", "fallback") if expect["kind"] == "answer" else ("abstention",))
            if "ids" in expect:
                ok = ok and got_ids == sorted(expect["ids"])
            if "banner" in expect:
                ok = ok and any(b["level"] == expect["banner"] for b in records.get("banners", []))
            if "language" in expect:
                ok = ok and answer.get("language") == expect["language"]
            called = sorted({c["tool"] for c in trace.get("tool_calls", [])})
            if "tools" in expect:
                t["tools"].add(called == expect["tools"], f"{label} {called} au lieu de {expect['tools']}")
            problems = (trace.get("check") or {}).get("problems")
            t["exact"].add(ok, f"{label} → {answer.get('kind')} {got_ids} {problems or trace.get('abstention')}")
            if case.get("held_out"):
                t["held_out"].add(ok, label)
            if expect["kind"] == "abstention":
                t["abstain_ok"].add(answer.get("kind") == "abstention", label)
            else:
                t["abstain_wrong"].add(answer.get("kind") != "abstention", label)  # réussite = pas d'abstention à tort
                t["checked"].add(answer.get("kind") == "answer", f"{label} {problems}")
                ctx = answer.get("context", {})
                t["cited"].add(bool(ctx.get("line") and answer.get("mention")), label)
            details.append(
                {
                    "id": case["id"],
                    "intent": case.get("intent", "socle"),
                    "ok": ok,
                    "kind": answer.get("kind"),
                    "ids": got_ids,
                    "tools": called,
                    "problems": problems,
                    "abstention": trace.get("abstention"),
                    "text": answer.get("text"),
                    "seconds": round(durations[-1], 1),
                }
            )
            print(
                f"{label:<34} {answer.get('kind', 'erreur'):<11} {'ok' if ok else 'KO'} {durations[-1]:6.1f} s  "
                f"{(answer.get('text') or '')[:80]}"
            )

    print(f"\nModèle : {trace.get('model_id')} · invites {trace.get('prompt_version')} · jeu {reference['version']}")
    for key, name in METRICS.items():
        print(t[key].line(name))
    durations.sort()
    print(f"Durée médiane {durations[len(durations) // 2]:.1f} s · maximale {durations[-1]:.1f} s")
    for f in t["exact"].failures:
        print("  échec :", f)
    if args.json:
        by_intent: dict[str, dict[str, int]] = {}
        for d in details:
            row = by_intent.setdefault(d["intent"], {"ok": 0, "n": 0})
            row["ok"] += d["ok"]
            row["n"] += 1
        report = {
            "label": args.label or trace.get("model_id"),
            "model_id": trace.get("model_id"),
            "prompt_version": trace.get("prompt_version"),
            "reference_version": reference["version"],
            "cases": len(cases),
            "repeat": args.repeat,
            "metrics": {k: {"ok": t[k].ok, "n": t[k].n, "ci95": wilson(t[k].ok, t[k].n)} for k in METRICS},
            "by_intent": by_intent,
            "median_s": durations[len(durations) // 2],
            "max_s": durations[-1],
            "details": details,
        }
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0 if not t["exact"].failures else 1


if __name__ == "__main__":
    sys.exit(main())
