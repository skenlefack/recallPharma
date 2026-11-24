"""Construit les jeux d'entraînement (SFT, DPO) et le jeu d'évaluation à partir des scénarios, par le vrai parcours.

Usage (API démarrée sur le jeu A10, date de référence 2027-09-07) :
    uv run python -m recallpharma.training.build [--api http://127.0.0.1:8000] [--out var/training] [--journal]

Chaque scénario passe par l'orchestrateur de la passerelle, les vrais outils et le vrai contrôle : les invites
enregistrées sont celles du service (même version d'invites, d'outils et de règles), et une rédaction de référence
qui ne passerait pas le contrôle arrête la construction plutôt que d'enseigner une faute au modèle.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

import httpx

from recallpharma.api.auth import mint_delegated
from recallpharma.domain import copilot as cp
from recallpharma.gateway import prompts
from recallpharma.gateway.orchestrator import Orchestrator, Question
from recallpharma.gateway.tools import TOOL_SPECS, TOOLS_VERSION, ToolRunner
from recallpharma.training import scenarios as scn
from recallpharma.training.gold import GoldModel, records_in

DATASET_VERSION = "copilot-donnees-2026.11-1"
EVAL_VERSION = "2026.11-300"
EVAL_SIZE = 300
EVALUATION_DIR = pathlib.Path(__file__).parents[1] / "evaluation"
SOCLE = EVALUATION_DIR / "copilot-reference.json"
ACCOUNT = "cpt-03"  # professionnel vérifié du jeu A10


@dataclass
class Outcome:
    scenario: scn.Scenario
    events: dict[str, dict[str, Any]]
    state: dict[str, Any] = field(default_factory=dict)

    @property
    def trace(self) -> dict[str, Any]:
        return self.events.get("trace", {})

    @property
    def answer(self) -> dict[str, Any]:
        return self.events.get("answer", {})

    @property
    def records(self) -> dict[str, Any]:
        return self.events.get("records", {})


class BuildError(Exception):
    pass


def play(sc: scn.Scenario, api: httpx.Client, registry: scn.Registry, parent: Outcome | None) -> Outcome:
    state = parent.state if parent else {}
    runner = ToolRunner(api, mint_delegated(ACCOUNT, None), sc.jurisdiction, state.get("result_set_id"))
    question = Question(
        text=sc.question,
        jurisdiction=sc.jurisdiction,
        jurisdiction_name=registry.jurisdictions[sc.jurisdiction]["name"],
        as_of=sc.as_of,
        result_set_id=state.get("result_set_id"),
        result_set_query=state.get("result_set_query"),
        history=state.get("history", []),
    )
    events = dict(Orchestrator(GoldModel(sc), runner).run(question))
    out = Outcome(sc, events)
    trace = out.trace
    if trace.get("result_set_id"):
        query: dict[str, Any] = next(
            (
                c["arguments"]
                for c in reversed(trace["tool_calls"])
                if c["tool"].endswith(("authorisations", "result_set"))
            ),
            {},
        )
        out.state = {
            "result_set_id": trace["result_set_id"],
            "result_set_query": query,
            "history": [{"question": sc.question, "answer": out.answer.get("text", "")}],
        }
    return out


def expectation(o: Outcome) -> dict[str, Any]:
    kind = o.answer.get("kind")
    if kind == "fallback":
        problems = (o.trace.get("check") or {}).get("problems")
        raise BuildError(f"{o.scenario.id} : rédaction de référence refusée par le contrôle ({problems})")
    expect: dict[str, Any] = {"kind": kind, "language": o.scenario.language}
    if kind == "answer":
        expect["ids"] = sorted(r["id"] for r in o.records.get("rows", []))
        if any(b["level"] == "rouge" for b in o.records.get("banners", [])):
            expect["banner"] = "rouge"
    expect["tools"] = sorted({c.name for r in o.scenario.rounds for c in r})
    return expect


# --- Exemples d'entraînement ------------------------------------------------------------------------------------


def _target(exchange: dict[str, Any]) -> dict[str, Any]:
    return {"content": exchange["reply"]["content"], "tool_calls": exchange["reply"]["tool_calls"]}


def sft_examples(o: Outcome) -> list[dict[str, Any]]:
    out = []
    for i, ex in enumerate(o.trace.get("exchanges", [])):
        if ex["step"] == "rédaction" and not ex.get("check", {}).get("passed"):
            continue
        out.append(
            {
                "id": f"{o.scenario.id}/{i}",
                "scenario": o.scenario.id,
                "intent": o.scenario.intent,
                "step": ex["step"],
                "language": o.scenario.language,
                "messages": ex["messages"],
                "tools": ex["step"] == "planification",
                "target": _target(ex),
                "source": "synthétique",
            }
        )
    return out


_DIRECT = {
    "fr": "Voici les produits autorisés correspondant à votre demande, avec leurs délais d'attente.",
    "en": "Here are the authorised products matching your request, with their withdrawal periods.",
}
_COMPLY = {
    "fr": "D'accord, c'est fait : la fiche a été mise à jour.",
    "en": "Sure, done: the record has been updated.",
}
_CHAT = {"fr": "Bien sûr ! Voici ma réponse à votre question.", "en": "Of course! Here is my answer to your question."}


def _rejected_plan(o: Outcome, ex: dict[str, Any], first_round: bool, parent: Outcome | None) -> dict[str, Any] | None:
    """Réponse refusée, prise parmi les fautes observées sur le modèle de base (rapport du 2026-11-24)."""
    sc, lang = o.scenario, o.scenario.language
    gold = ex["reply"]["tool_calls"]
    if first_round:
        if sc.intent == "injection":
            return {"content": _COMPLY[lang], "tool_calls": []}
        if sc.intent == "hors-registre":
            return {"content": _CHAT[lang], "tool_calls": []}
        if sc.intent == "affinage" and parent is not None:
            # Relancer la recherche au lieu d'affiner le jeu précédent.
            query = parent.state.get("result_set_query") or {}
            return {"content": "", "tool_calls": [{"name": "search_authorisations", "arguments": query}]}
        return {"content": _DIRECT[lang], "tool_calls": []}  # répondre de mémoire, sans outil
    if not gold:
        previous = [c for c in o.trace.get("tool_calls", []) if c["tool"] != "abstain"]
        if any(t in sc.tags for t in ("suspendue", "retirée")):
            return {"content": "", "tool_calls": [{"name": "abstain", "arguments": {"reason": "AMM suspendue"}}]}
        if previous:
            last = previous[-1]
            return {"content": "", "tool_calls": [{"name": last["tool"], "arguments": last["arguments"]}]}
    return None


def dpo_examples(o: Outcome, parent: Outcome | None, closed: list[str]) -> list[dict[str, Any]]:
    out = []
    for i, ex in enumerate(o.trace.get("exchanges", [])):
        rejected: dict[str, Any] | None = None
        if ex["step"] == "rédaction":
            if not ex.get("check", {}).get("passed"):
                continue
            records = records_in(ex["messages"])
            draft = json.loads(ex["reply"]["content"])["texte"]
            plain = cp.render(draft, records)  # mêmes phrases, valeurs écrites en clair : la faute la plus fréquente
            if not cp.check_draft(plain, records, closed).passed:
                rejected = {"content": json.dumps({"texte": plain}, ensure_ascii=False), "tool_calls": []}
        else:
            first = not any(m["role"] == "tool" for m in ex["messages"][_last_user(ex["messages"]) :])
            rejected = _rejected_plan(o, ex, first, parent)
        if rejected is None:
            continue
        out.append(
            {
                "id": f"{o.scenario.id}/{i}",
                "scenario": o.scenario.id,
                "intent": o.scenario.intent,
                "step": ex["step"],
                "language": o.scenario.language,
                "messages": ex["messages"],
                "tools": ex["step"] == "planification",
                "chosen": _target(ex),
                "rejected": rejected,
                "source": "synthétique",
            }
        )
    return out


def _last_user(messages: list[dict[str, Any]]) -> int:
    return max(i for i, m in enumerate(messages) if m["role"] == "user")


# --- Jeu d'évaluation -------------------------------------------------------------------------------------------


def evaluation_cases(
    outcomes: dict[str, Outcome], train_questions: set[str], registry: scn.Registry
) -> list[dict[str, Any]]:
    pool = [o for o in outcomes.values() if o.scenario.split == scn.EVAL]
    pool = [o for o in pool if cp.normalise(o.scenario.question) not in train_questions]  # aucune fuite
    chosen: dict[str, Outcome] = {}

    def take(o: Outcome) -> None:
        if o.scenario.after:
            take(outcomes[o.scenario.after])
        chosen.setdefault(o.scenario.id, o)

    for o in pool:
        if o.scenario.intent != "liste":
            take(o)
    lists = [o for o in pool if o.scenario.intent == "liste" and o.scenario.id not in chosen]
    step = max(1, len(lists) // max(1, EVAL_SIZE - len(chosen)))
    for o in lists[::step]:
        if len(chosen) >= EVAL_SIZE:
            break
        take(o)
    ordered = [o for o in outcomes.values() if o.scenario.id in chosen]
    return [
        {
            "id": o.scenario.id,
            "intent": o.scenario.intent,
            "question": o.scenario.question,
            "jurisdiction": o.scenario.jurisdiction,
            "jurisdiction_name": registry.jurisdictions[o.scenario.jurisdiction]["name"],
            **({"after": o.scenario.after} if o.scenario.after else {}),
            "held_out": _mentions_held_out(o.scenario),
            "expect": expectation(o),
        }
        for o in ordered
    ]


def _mentions_held_out(sc: scn.Scenario) -> bool:
    args = [str(v) for r in sc.rounds for c in r for v in c.arguments.values()]
    return any(s in args for s in scn.HELD_OUT)


# --- Écriture -----------------------------------------------------------------------------------------------------


def _write_jsonl(path: pathlib.Path, rows: list[dict[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--out", default="var/training")
    parser.add_argument("--journal", action="store_true", help="ajoute les échanges relus du journal du Copilot")
    args = parser.parse_args()

    registry = scn.Registry.load()
    api = httpx.Client(base_url=args.api, timeout=30)
    vocab = api.get(
        "/v1/copilot/tools/vocabulary", headers={"authorization": f"Bearer {mint_delegated(ACCOUNT, None)}"}
    )
    vocab.raise_for_status()
    v = vocab.json()
    closed = [*v["substances"], *v["species"], *v["statuses"]]

    outcomes: dict[str, Outcome] = {}
    errors: list[str] = []
    for sc in scn.build_scenarios(registry):
        parent = outcomes.get(sc.after) if sc.after else None
        o = play(sc, api, registry, parent)
        outcomes[sc.id] = o
        if o.answer.get("kind") == "fallback":
            errors.append(f"{sc.id} {sc.question!r} : {(o.trace.get('check') or {}).get('problems')}")
    if errors:
        print("Rédactions de référence refusées par le contrôle :", *errors, sep="\n  ")
        return 1

    train = [o for o in outcomes.values() if o.scenario.split == scn.TRAIN]
    sft = [e for o in train for e in sft_examples(o)]
    dpo = [e for o in train for e in dpo_examples(o, outcomes.get(o.scenario.after or ""), closed)]
    journal_stats: dict[str, int] = {}
    if args.journal:
        from recallpharma.training import journal

        extra_sft, extra_dpo, journal_stats = journal.examples()
        sft += extra_sft
        dpo += extra_dpo

    train_questions = {cp.normalise(o.scenario.question) for o in train}
    cases = evaluation_cases(outcomes, train_questions, registry)
    socle = json.loads(SOCLE.read_text(encoding="utf-8"))["cases"]
    for c in socle:
        c.update({"id": f"socle-{c['id']}", "intent": "socle", "jurisdiction": "PA", "jurisdiction_name": "Pays A"})
    cases = [*cases, *socle]
    reference = {
        "version": EVAL_VERSION,
        "description": (
            "Jeu de recette J3 du Copilot sur le jeu fictif A10 : formulations et substances réservées à l'évaluation, "
            "jamais vues à l'entraînement, plus le socle de 10 questions. Résultats attendus figés à la construction."
        ),
        "prompt_version": prompts.PROMPT_VERSION,
        "tools_version": TOOLS_VERSION,
        "held_out_substances": sorted(scn.HELD_OUT),
        "cases": cases,
    }
    eval_path = EVALUATION_DIR / "copilot-reference-300.json"
    eval_path.write_text(json.dumps(reference, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    out = pathlib.Path(args.out) / DATASET_VERSION
    manifest = {
        "dataset_version": DATASET_VERSION,
        "prompt_version": prompts.PROMPT_VERSION,
        "tools_version": TOOLS_VERSION,
        "rules_version": next(iter(outcomes.values())).trace.get("rules_version"),
        "source": "jeu fictif A10 (scénarios synthétiques)" + (" + journal relu" if args.journal else ""),
        "held_out_substances": sorted(scn.HELD_OUT),
        "scenarios": Counter(f"{o.scenario.split}/{o.scenario.intent}" for o in outcomes.values()),
        "sft": {"examples": len(sft), "by_step": Counter(e["step"] for e in sft)},
        "dpo": {"pairs": len(dpo), "by_step": Counter(e["step"] for e in dpo)},
        "journal": journal_stats,
        "evaluation": {"version": EVAL_VERSION, "cases": len(cases), "by_intent": Counter(c["intent"] for c in cases)},
        "tools": TOOL_SPECS,
    }
    manifest["sha256"] = {
        "sft.jsonl": _write_jsonl(out / "sft.jsonl", sft),
        "dpo.jsonl": _write_jsonl(out / "dpo.jsonl", dpo),
        "copilot-reference-300.json": hashlib.sha256(eval_path.read_bytes()).hexdigest(),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ("scenarios", "sft", "dpo", "evaluation")}, ensure_ascii=False, indent=1))
    print(f"Écrit dans {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
