"""Rejoue le jeu de référence contre la passerelle et le modèle réels ; rapporte les métriques de CT-IA-01.

Usage (API et passerelle démarrées, modèle servi) :
    uv run python -m recallpharma.evaluation.copilot_eval [--repeat 3] [--gateway http://127.0.0.1:8001]

Métriques : exactitude (bons enregistrements, bon type de réponse), abstention correcte, abstention à tort,
contrôle après génération réussi, mentions RG-26 présentes. Intervalles de confiance à 95 % (Wilson).
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


def ask(gateway: httpx.Client, question: str, state: dict[str, Any]) -> dict[str, Any]:
    body = {
        "question": question,
        "jurisdiction": "PA",
        "jurisdiction_name": "Pays A",
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gateway", default="http://127.0.0.1:8001")
    parser.add_argument("--repeat", type=int, default=1)
    args = parser.parse_args()
    reference = json.loads(REFERENCE.read_text(encoding="utf-8"))
    gateway = httpx.Client(base_url=args.gateway, timeout=600)

    exact, abstain_ok, abstain_wrong, checked, cited = Tally(), Tally(), Tally(), Tally(), Tally()
    durations: list[float] = []
    for run in range(args.repeat):
        states: dict[str, dict[str, Any]] = {}
        for case in reference["cases"]:
            label = f"{case['id']}#{run + 1}"
            state = states.get(case.get("after", ""), {})
            t0 = time.monotonic()
            out = ask(gateway, case["question"], state)
            durations.append(time.monotonic() - t0)
            trace, answer, records = out.get("trace", {}), out.get("answer", {}), out.get("records", {})
            if trace.get("result_set_id"):
                states[case["id"]] = {"result_set_id": trace["result_set_id"], "result_set_query": {}}
            expect = case["expect"]
            got_ids = sorted(r["id"] for r in records.get("rows", []))
            ok = answer.get("kind") in (("answer", "fallback") if expect["kind"] == "answer" else ("abstention",))
            if "ids" in expect:
                ok = ok and got_ids == sorted(expect["ids"])
            if "banner" in expect:
                ok = ok and any(b["level"] == expect["banner"] for b in records.get("banners", []))
            if "language" in expect:
                ok = ok and answer.get("language") == expect["language"]
            exact.add(ok, f"{label} → {answer.get('kind')} {got_ids} {answer.get('text', out.get('error'))!r}")
            if expect["kind"] == "abstention":
                abstain_ok.add(answer.get("kind") == "abstention", label)
            else:
                abstain_wrong.add(answer.get("kind") != "abstention", label)  # réussite = pas d'abstention à tort
                checked.add(answer.get("kind") == "answer", f"{label} {(trace.get('check') or {}).get('problems')}")
                ctx = answer.get("context", {})
                cited.add(bool(ctx.get("line") and answer.get("mention")), label)
            print(
                f"{label:<34} {answer.get('kind', 'erreur'):<11} {durations[-1]:5.1f} s  {answer.get('text', '')[:90]}"
            )

    print(f"\nModèle : {trace.get('model_id')} · invites {trace.get('prompt_version')} · jeu {reference['version']}")
    print(exact.line("Exactitude"))
    print(abstain_ok.line("Abstention correcte"))
    print(abstain_wrong.line("Sans abstention à tort"))
    print(checked.line("Contrôle réussi (sans repli)"))
    print(cited.line("Contexte et mention (RG-26)"))
    durations.sort()
    print(f"Durée médiane {durations[len(durations) // 2]:.1f} s · maximale {durations[-1]:.1f} s")
    for f in exact.failures:
        print("  échec :", f)
    return 0 if not exact.failures else 1


if __name__ == "__main__":
    sys.exit(main())
