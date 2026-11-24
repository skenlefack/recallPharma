"""Jeux d'entraînement : partage sans fuite, modèle de référence, règle de promotion (sans base ni GPU)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from recallpharma.domain import copilot as cp
from recallpharma.training import scenarios as scn
from recallpharma.training.chat import parse_reply, to_hf
from recallpharma.training.gold import GoldModel, choose_draft, fill
from recallpharma.training.promote import decide
from recallpharma.training.recipe import stratified


@pytest.fixture(scope="module")
def all_scenarios() -> list[scn.Scenario]:
    return scn.build_scenarios()


def _arguments(sc: scn.Scenario) -> list[str]:
    return [str(v) for r in sc.rounds for c in r for v in c.arguments.values()]


def test_scenarios_are_stable(all_scenarios: list[scn.Scenario]) -> None:
    again = scn.build_scenarios()
    assert [s.to_json() for s in again] == [s.to_json() for s in all_scenarios]


def test_held_out_substances_never_reach_training(all_scenarios: list[scn.Scenario]) -> None:
    for sc in all_scenarios:
        if sc.split == scn.TRAIN:
            assert not set(_arguments(sc)) & scn.HELD_OUT, sc.id
            assert not any(h in cp.normalise(sc.question) for h in map(cp.normalise, scn.HELD_OUT)), sc.id
    assert any(set(_arguments(sc)) & scn.HELD_OUT for sc in all_scenarios if sc.split == scn.EVAL)


def test_evaluation_phrasings_are_never_used_for_training() -> None:
    for table in (scn.LIST_SPECIES, scn.LIST_PLAIN, scn.STATUS, scn.SHEET, scn.DELAY, scn.END, scn.OFF_TOPIC):
        assert not set(table[scn.TRAIN]) & set(table[scn.EVAL])


def test_refinements_follow_their_parent_in_the_same_split(all_scenarios: list[scn.Scenario]) -> None:
    seen: dict[str, scn.Scenario] = {}
    for sc in all_scenarios:
        if sc.after:
            parent = seen[sc.after]  # le parent précède : l'état de conversation existe déjà
            assert parent.split == sc.split and parent.jurisdiction == sc.jurisdiction
            assert [c.name for r in sc.rounds for c in r] == ["refine_result_set"]
        seen[sc.id] = sc


def test_every_scenario_teaches_a_tool_or_a_screened_abstention(all_scenarios: list[scn.Scenario]) -> None:
    for sc in all_scenarios:
        names = {c.name for r in sc.rounds for c in r}
        if sc.intent == "hors-perimetre":
            assert cp.screen_question(sc.question), sc.question  # écartée sans modèle : jamais d'exemple d'entraînement
            assert not names
        else:
            assert not cp.screen_question(sc.question), sc.question
            assert names, sc.id
        if sc.intent in ("hors-registre", "injection"):
            assert names == {"abstain"}


def test_reference_drafts_pass_the_check_on_their_own_records() -> None:
    records = {
        "liste1": {"total": "2", "excluded": "0", "apart": "0", "jurisdiction": "PA"},
        "amm-007": {"name": "Produit-007", "designation": "ivermectine 10 mg/mL", "status": "valide"},
        "amm-023": {"name": "Produit-023", "designation": "ivermectine 10 mg/mL", "status": "valide"},
    }
    closed = ["ivermectine", "bovins", "valide", "suspendue"]
    for template in scn.LIST_FR + scn.LIST_EN:
        text = fill(template, records)
        assert text and cp.check_draft(text, records, closed).passed, template
        # La faute enseignée comme refusée (DPO) : les mêmes phrases, valeurs en clair.
        assert not cp.check_draft(cp.render(text, records), records, closed).passed


def test_draft_choice_follows_the_result() -> None:
    refine = scn.Scenario("affinage-x", "affinage", scn.TRAIN, "Lesquels ?", "PA", (), scn.REFINE_FR)
    one = {"liste1": {"total": "1"}, "amm-001": {"name": "P", "designation": "d"}}
    none = {"liste1": {"total": "0"}}
    assert "un seul produit" in (choose_draft(refine, one) or "") or "Un seul" in (choose_draft(refine, one) or "")
    assert (choose_draft(refine, none) or "").startswith("Aucun")
    delay = scn.Scenario("delai-x", "delai", scn.TRAIN, "Délai ?", "PA", (), scn.DELAY_FR)
    assert "ne donne pas" in (choose_draft(delay, {"amm-001": {"name": "P"}}) or "")
    with_delay = {"amm-001": {"name": "P"}, "amm-001#delai2": {"value": "7 jours", "route": "IM"}}
    assert "[[amm-001#delai2:value]]" in (choose_draft(delay, with_delay) or "")


def _tool(result: dict[str, Any]) -> dict[str, Any]:
    return {"role": "tool", "content": "<donnees_outil>\n" + json.dumps(result) + "\n</donnees_outil>"}


def test_gold_model_reads_only_the_messages() -> None:
    sc = scn.Scenario(
        "delai-y",
        "delai",
        scn.TRAIN,
        "Délai lait du Produit-001 ?",
        "PA",
        (
            (scn.Call("search_authorisations", {"product_name": "Produit-001"}),),
            (scn.Call("get_withdrawal_periods", {"ma_id": scn.FIRST_ROW, "commodity": "lait"}),),
        ),
        scn.DELAY_FR,
    )
    gold = GoldModel(sc)
    messages: list[dict[str, Any]] = [{"role": "system", "content": "…"}, {"role": "user", "content": "q"}]
    first = gold.complete(messages, tools=[])
    assert [c.name for c in first.tool_calls] == ["search_authorisations"]
    messages += [
        {"role": "assistant", "content": "", "tool_calls": [{"id": "a"}]},
        _tool({"lignes": [{"id": "amm-001"}]}),
    ]
    second = gold.complete(messages, tools=[])
    assert second.tool_calls[0].arguments == {"ma_id": "amm-001", "commodity": "lait"}
    messages += [{"role": "assistant", "content": "", "tool_calls": [{"id": "b"}]}, _tool({"delais": {}})]
    assert gold.complete(messages, tools=[]).tool_calls == []  # données suffisantes : plus d'appel
    # Recherche vide : la référence s'arrête, c'est le parcours qui s'abstient.
    empty = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "content": "", "tool_calls": [{}]},
        _tool({"lignes": []}),
    ]
    assert gold.complete(empty, tools=[]).tool_calls == []


def test_tool_calls_round_trip_through_the_template_format() -> None:
    reply = parse_reply('<tool_call>\n{"name": "search_authorisations", "arguments": {"substance": "x"}}\n</tool_call>')
    assert reply["content"] == "" and reply["tool_calls"][0]["function"]["name"] == "search_authorisations"
    assert json.loads(reply["tool_calls"][0]["function"]["arguments"]) == {"substance": "x"}
    assert parse_reply('{"texte": "a"}') == {"role": "assistant", "content": '{"texte": "a"}', "tool_calls": []}
    assert parse_reply("<tool_call>{pas du json}</tool_call>")["tool_calls"] == []
    hf = to_hf([{"role": "assistant", "content": "", "tool_calls": [reply["tool_calls"][0]]}])
    assert hf[0]["tool_calls"][0]["function"]["arguments"] == {"substance": "x"}  # objet, pas chaîne JSON


def test_stratified_sample_keeps_every_group() -> None:
    rows = [
        {"intent": i, "step": s, "n": k}
        for i in ("a", "b", "c")
        for s in ("p", "r")
        for k in range(20 if i == "a" else 3)
    ]
    sample = stratified(rows, 20, seed=1)
    assert len(sample) <= 20 and {(r["intent"], r["step"]) for r in sample} == {(r["intent"], r["step"]) for r in rows}
    assert stratified(rows, 20, seed=1) == sample
    assert len(stratified(rows, None, seed=1)) == len(rows)


def _report(**rates: tuple[int, int]) -> dict[str, Any]:
    keys = ("exact", "abstain_ok", "abstain_wrong", "checked", "cited", "tools", "held_out")
    metrics = {k: {"ok": rates.get(k, (10, 10))[0], "n": rates.get(k, (10, 10))[1]} for k in keys}
    return {"label": "x", "reference_version": "v", "cases": 10, "metrics": metrics}


def test_promotion_rule() -> None:
    assert decide(_report(), _report()) == (True, [])
    ok, reasons = decide(_report(abstain_ok=(9, 10)), None)
    assert not ok and "sécurité" in reasons[0]  # une abstention manquée suffit à refuser
    ok, reasons = decide(_report(exact=(9, 10)), _report(exact=(10, 10)), min_exact=0.5)
    assert not ok and "régression" in reasons[0]  # l'exactitude ne baisse jamais
    assert decide(_report(tools=(97, 100)), {**_report(tools=(98, 100))}, min_exact=0.5)[0]  # tolérance de 2 points
    assert not decide(_report(exact=(8, 10)), None)[0]  # sous le seuil de 90 %
    other = {**_report(), "cases": 20}
    assert decide(_report(), other) == (False, ["rapports non comparables : jeu ou échantillon différent"])
