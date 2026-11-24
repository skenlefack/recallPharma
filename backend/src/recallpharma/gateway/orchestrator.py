"""Parcours d'une question (D6) : sept étapes, dont deux seulement confiées au modèle (planification, rédaction).

Événements émis, dans l'ordre : `status`, `records` (bandeaux et tableau, composés sans le modèle, dès la fin des
outils), `answer` (texte contrôlé, d'un bloc), puis `trace` pour le journal de l'API.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from recallpharma.domain import copilot as cp
from recallpharma.gateway import prompts
from recallpharma.gateway.llm import ChatModel, ModelUnavailable, Reply, ToolCall
from recallpharma.gateway.tools import TOOL_SPECS, TOOLS_VERSION, ToolError, ToolRunner

MAX_TOOL_CALLS = 8
MAX_PLANNING_ROUNDS = 3
STATUS_EN = {
    "valide": "valid",
    "suspendue": "suspended",
    "retirée": "withdrawn",
    "renouvellement en instance": "renewal pending",
    "expirée, à confirmer": "expired, to be confirmed",
    "non vérifiable": "unverifiable",
}

Event = tuple[str, dict[str, Any]]


@dataclass
class Question:
    text: str
    jurisdiction: str
    jurisdiction_name: str
    as_of: str
    result_set_id: str | None = None
    result_set_query: dict[str, Any] | None = None
    history: list[dict[str, str]] = field(default_factory=list)  # 3 derniers échanges au plus


@dataclass
class Trace:
    model_id: str
    prompt_version: str = prompts.PROMPT_VERSION
    tools_version: str = TOOLS_VERSION
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    check: dict[str, Any] | None = None
    abstention: str | None = None
    injection_suspected: bool = False
    rules_version: str | None = None

    def count(self, reply: Reply) -> None:
        self.tokens_in += reply.tokens_in
        self.tokens_out += reply.tokens_out


def _data(value: Any) -> str:
    """Résultat d'outil présenté au modèle comme une donnée délimitée, jamais comme une instruction."""
    return "<donnees_outil>\n" + json.dumps(value, ensure_ascii=False, default=str) + "\n</donnees_outil>"


def _state(q: Question) -> str:
    if not q.result_set_id:
        return ""
    return (
        f"\nÉtat de la conversation : dernier jeu de résultats {q.result_set_id}, "
        f"obtenu par {json.dumps(q.result_set_query or {}, ensure_ascii=False)}. "
        "Une question qui le restreint (« lesquels… », « exclus… ») se traite par refine_result_set."
    )


class Orchestrator:
    def __init__(self, model: ChatModel, runner: ToolRunner) -> None:
        self.model, self.runner = model, runner

    def run(self, q: Question) -> Iterator[Event]:
        started = time.monotonic()
        trace = Trace(model_id=self.model.model_id, injection_suspected=cp.looks_like_injection(q.text))
        language = cp.detect_language(q.text)
        yield "status", {"step": "réception", "language": language}

        # 1. Réception : hors périmètre, abstention sans appeler le modèle (RG-25).
        reason = cp.screen_question(q.text)
        if reason:
            trace.abstention = reason
            yield from self._abstain(q, language, trace, reason, started)
            return

        try:
            vocabulary = self.runner.vocabulary()
        except ToolError:
            yield from self._unavailable(trace, started, "registre")
            return
        trace.rules_version = vocabulary.get("rules_version")

        # 2-4. Planification par le modèle, exécution par la passerelle.
        yield "status", {"step": "planification"}
        try:
            abstained = self._plan_and_execute(q, trace)
        except ModelUnavailable:
            yield from self._unavailable(trace, started, "modèle")
            return
        turn = self.runner.turn
        yield "records", self._records_event(q, language)

        if abstained is not None:
            trace.abstention = abstained
            yield from self._abstain(q, language, trace, abstained, started, records_shown=True)
            return
        # Une recherche vide n'est pas une donnée ; un affinage vide en est une (« aucun ne respecte le critère »).
        refined = any(
            t["tool"] == "refine_result_set" and "erreur" not in (t["result"] or {}) for t in trace.tool_calls
        )
        if not refined and not any(not rid.startswith("liste") for rid in turn.records):
            trace.abstention = "aucun résultat d'outil"
            yield from self._abstain(q, language, trace, trace.abstention, started, records_shown=True)
            return
        levels = [turn.meta[r["id"]]["evidence"] for r in turn.rows if r["id"] in turn.meta]
        if levels and all(lv == "D" for lv in levels):
            trace.abstention = "données de niveau D uniquement"  # RG-14, RG-25
            yield from self._abstain(q, language, trace, trace.abstention, started, records_shown=True)
            return

        # 5-6. Rédaction par le modèle, composition et contrôle déterministes.
        yield "status", {"step": "rédaction"}
        closed = [*vocabulary["substances"], *vocabulary["species"], *vocabulary["statuses"]]
        try:
            text, check, attempts = self._draft(q, language, closed, trace)
        except ModelUnavailable:
            text, check, attempts = None, cp.CheckResult(False, ("modèle indisponible à la rédaction",), ()), 0
        trace.check = {
            "passed": check.passed,
            "attempts": attempts,
            "problems": list(check.problems),
            "refs": [list(r) for r in check.refs],
        }
        cited = [r for r, _ in check.refs] if text else [r["id"] for r in turn.rows]
        yield "answer", self._answer(q, language, text, cited)
        yield "trace", self._trace(trace, started)

    # --- Planification --------------------------------------------------------------------------

    def _plan_and_execute(self, q: Question, trace: Trace) -> str | None:
        system = prompts.PLAN.format(
            jurisdiction=q.jurisdiction, jurisdiction_name=q.jurisdiction_name, as_of=q.as_of, state=_state(q)
        )
        messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
        for h in q.history[-3:]:
            messages += [{"role": "user", "content": h["question"]}, {"role": "assistant", "content": h["answer"]}]
        messages.append({"role": "user", "content": f"<question>\n{q.text}\n</question>"})
        budget = MAX_TOOL_CALLS
        for _ in range(MAX_PLANNING_ROUNDS):
            reply = self.model.complete(messages, tools=TOOL_SPECS, max_tokens=400)
            trace.count(reply)
            # Un appel identique à un appel déjà fait dans le tour n'est pas rejoué : rien de nouveau à apprendre.
            done = {(t["tool"], json.dumps(t["arguments"], sort_keys=True)) for t in trace.tool_calls}
            calls = [c for c in reply.tool_calls if (c.name, json.dumps(c.arguments, sort_keys=True)) not in done]
            calls = calls[:budget]
            if not calls:
                return None
            for c in calls:
                if c.name == "abstain":
                    trace.tool_calls.append({"tool": "abstain", "arguments": c.arguments, "result": None})
                    if self.runner.turn.records:
                        # Abstention demandée après obtention de données : la réception a déjà écarté le hors
                        # périmètre ; une AMM suspendue se dit avec son bandeau, elle ne justifie pas de se taire.
                        return None
                    return str(c.arguments.get("reason") or "hors périmètre")
            budget -= len(calls)
            messages.append(
                {
                    "role": "assistant",
                    "content": reply.content or "",
                    "tool_calls": [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {"name": c.name, "arguments": json.dumps(c.arguments, ensure_ascii=False)},
                        }
                        for c in calls
                    ],
                }
            )
            for c, result in zip(calls, self._execute(calls, trace), strict=True):
                messages.append({"role": "tool", "tool_call_id": c.id, "content": _data(result)})
            if budget <= 0:
                break
        return None

    def _execute(self, calls: list[ToolCall], trace: Trace) -> list[dict[str, Any]]:
        def one(c: ToolCall) -> tuple[dict[str, Any], int]:
            t0 = time.monotonic()
            if c.invalid:
                result = ToolError("invalid_arguments", c.invalid).as_result()
            else:
                try:
                    result = self.runner.run(c.name, c.arguments)
                except ToolError as e:
                    result = e.as_result()
            return result, int((time.monotonic() - t0) * 1000)

        # Les outils d'un même tour sont indépendants : lancés en parallèle (le jeu de résultats reste séquentiel).
        if len(calls) > 1 and not any(c.name == "refine_result_set" for c in calls):
            with ThreadPoolExecutor(max_workers=4) as pool:
                outcomes = list(pool.map(one, calls))
        else:
            outcomes = [one(c) for c in calls]
        for c, (result, ms) in zip(calls, outcomes, strict=True):
            trace.tool_calls.append({"tool": c.name, "arguments": c.arguments, "result": result, "duration_ms": ms})
        return [r for r, _ in outcomes]

    # --- Rédaction et contrôle (RG-23) -----------------------------------------------------------

    def _draft(
        self, q: Question, language: str, closed: list[str], trace: Trace
    ) -> tuple[str | None, cp.CheckResult, int]:
        records = self.runner.turn.records
        listing = "\n".join(
            f"{rid} : " + json.dumps(fields, ensure_ascii=False) for rid, fields in list(records.items())[:40]
        )
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": prompts.DRAFT.format(
                    language_name="anglais" if language == "en" else "français",
                    forbidden=", ".join(
                        sorted({t for t in closed if cp.normalise(t) in cp.normalise(q.text)} | set(cp.STATUS_WORDS))
                    ),
                ),
            },
            {
                "role": "user",
                "content": f"<question>\n{q.text}\n</question>\n<enregistrements>\n{listing}\n</enregistrements>",
            },
        ]
        check = cp.CheckResult(False, ("aucune rédaction",), ())
        for attempt in (1, 2):
            reply = self.model.complete(messages, json_mode=True, max_tokens=300)
            trace.count(reply)
            draft = _draft_text(reply.content)
            check = cp.check_draft(draft, records, closed)
            if check.passed:
                return self._localise(cp.render(draft, records), language), check, attempt
            messages += [
                {"role": "assistant", "content": reply.content},
                {"role": "user", "content": prompts.RETRY.format(problems="; ".join(check.problems))},
            ]
        return None, check, 2

    @staticmethod
    def _localise(text: str, language: str) -> str:
        if language != "en":
            return text
        for fr, en in STATUS_EN.items():
            text = text.replace(fr, en)
        return text

    # --- Composition (RG-15, RG-26) ---------------------------------------------------------------

    def _records_event(self, q: Question, language: str) -> dict[str, Any]:
        t = self.runner.turn
        red_first = sorted(t.banners, key=lambda b: {"rouge": 0, "orange": 1}.get(b["level"], 2))
        return {
            "banners": red_first,
            "rows": t.rows,
            "total": t.total,
            "apart": t.apart,
            "elsewhere": t.elsewhere,
            "notices": t.notices,
            "result_set_id": t.result_set_id,
            "jurisdiction": q.jurisdiction,
        }

    def _context(self, q: Question, cited: list[str], language: str) -> dict[str, Any]:
        """RG-26 sur les données citées : citer un total de liste, c'est citer toutes les lignes de la liste."""
        turn = self.runner.turn
        meta = turn.meta
        expanded: list[str] = []
        for rid in cited:
            base = rid.split("#")[0]
            expanded += [r["id"] for r in turn.rows] if base.startswith("liste") else [base]
        ids = [i for i in dict.fromkeys(expanded) if i in meta]
        ctx = cp.context(
            q.jurisdiction_name,
            [meta[i]["verified_at"] for i in ids],
            [meta[i]["evidence"] for i in ids if meta[i]["evidence"]],
            [meta[i]["source"] for i in ids if meta[i]["source"]],
        )
        return {
            "line": ctx.line(language),
            "jurisdiction": q.jurisdiction,
            "oldest_verification": ctx.oldest_verification,
            "weakest_evidence": ctx.weakest_evidence,
            "sources": list(ctx.sources),
        }

    def _answer(self, q: Question, language: str, text: str | None, cited: list[str]) -> dict[str, Any]:
        en = language == "en"
        record_ids = [i for i in dict.fromkeys(r.split("#")[0] for r in cited) if i.startswith("amm-")]
        return {
            "kind": "answer" if text else "fallback",
            "text": text or (cp.CHECK_FAILED_EN if en else cp.CHECK_FAILED),
            "context": self._context(q, cited, language),
            "mention": cp.MENTION_EN if en else cp.MENTION,
            "actions": [{"label": "Afficher la fiche", "href": f"/amm/{i}"} for i in record_ids[:3]]
            + [{"label": "Signaler une erreur", "action": "feedback"}],
            "language": language,
        }

    def _abstain(
        self,
        q: Question,
        language: str,
        trace: Trace,
        reason: str,
        started: float,
        records_shown: bool = False,
    ) -> Iterator[Event]:
        if not records_shown:
            yield (
                "records",
                {
                    "banners": [],
                    "rows": [],
                    "total": None,
                    "apart": [],
                    "elsewhere": [],
                    "notices": [],
                    "result_set_id": None,
                    "jurisdiction": q.jurisdiction,
                },
            )
        en = language == "en"
        turn = self.runner.turn
        available = [r["id"] for r in turn.rows] + [r["id"] for r in turn.elsewhere]
        yield (
            "answer",
            {
                "kind": "abstention",
                "reason": reason,
                "text": cp.ABSTENTION_EN if en else cp.ABSTENTION,
                "context": self._context(q, available, language),
                "mention": cp.MENTION_EN if en else cp.MENTION,
                "actions": [{"label": "Rechercher dans le registre", "href": "/"}],
                "language": language,
            },
        )
        yield "trace", self._trace(trace, started)

    def _unavailable(self, trace: Trace, started: float, what: str) -> Iterator[Event]:
        trace.abstention = f"{what} indisponible"
        yield "error", {"code": "copilot_unavailable", "message": cp.UNAVAILABLE}
        yield "trace", self._trace(trace, started)

    def _trace(self, trace: Trace, started: float) -> dict[str, Any]:
        return {
            "model_id": trace.model_id,
            "prompt_version": trace.prompt_version,
            "tools_version": trace.tools_version,
            "rules_version": trace.rules_version,
            "tool_calls": trace.tool_calls,
            "tokens_in": trace.tokens_in,
            "tokens_out": trace.tokens_out,
            "check": trace.check,
            "abstention": trace.abstention,
            "injection_suspected": trace.injection_suspected,
            "result_set_id": self.runner.turn.result_set_id,
            "duration_ms": int((time.monotonic() - started) * 1000),
        }


def _draft_text(content: str) -> str:
    try:
        value = json.loads(content)
    except json.JSONDecodeError:
        return content
    if isinstance(value, dict):
        for key in ("texte", "text", "reponse", "réponse"):
            if isinstance(value.get(key), str):
                return str(value[key])
    return ""
