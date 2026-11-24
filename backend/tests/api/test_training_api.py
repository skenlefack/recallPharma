"""Jeux d'entraînement par le vrai parcours : chaque rédaction de référence passe le contrôle, le journal relu alimente
l'entraînement et un retour « erreur signalée » n'y entre jamais."""

from __future__ import annotations

import json
from collections import Counter

import pytest
from fastapi.testclient import TestClient

from recallpharma.api.auth import mint_delegated
from recallpharma.domain import copilot as cp
from recallpharma.gateway import prompts
from recallpharma.gateway.tools import TOOL_NAMES
from recallpharma.training import build, journal
from recallpharma.training import scenarios as scn
from recallpharma.training.gold import records_in
from tests.api.test_copilot_api import PRO, ScriptedModel, ask, conversation, first, model  # noqa: F401

pytestmark = pytest.mark.db


def test_every_scenario_plays_through_the_real_pipeline(client: TestClient) -> None:
    registry = scn.Registry.load()
    v = client.get(
        "/v1/copilot/tools/vocabulary", headers={"authorization": f"Bearer {mint_delegated('cpt-03', None)}"}
    )
    closed = [*v.json()["substances"], *v.json()["species"], *v.json()["statuses"]]
    outcomes: dict[str, build.Outcome] = {}
    kinds: Counter[str] = Counter()
    for sc in scn.build_scenarios(registry):
        o = build.play(sc, client, registry, outcomes.get(sc.after or ""))
        outcomes[sc.id] = o
        kinds[o.answer["kind"]] += 1
        # Aucune rédaction de référence refusée : on n'enseigne jamais au modèle une réponse que le contrôle rejette.
        assert o.answer["kind"] != "fallback", (sc.id, o.trace.get("check"))
        if sc.intent == "hors-perimetre":
            assert o.trace["exchanges"] == []  # écartée à la réception, le modèle n'est pas appelé
            continue
        called = [c["tool"] for c in o.trace["tool_calls"]]
        assert set(called) <= TOOL_NAMES and called, sc.id
        if sc.split != scn.TRAIN:
            continue
        for ex in build.sft_examples(o):
            assert ex["messages"][0]["role"] == "system"
            if ex["step"] == "planification":
                assert ex["messages"][0]["content"].startswith(prompts.PLAN[:40])
            else:
                draft = json.loads(ex["target"]["content"])["texte"]
                assert cp.check_draft(draft, records_in(ex["messages"]), closed).passed
        for pair in build.dpo_examples(o, outcomes.get(sc.after or ""), closed):
            assert pair["chosen"] != pair["rejected"]
            if pair["step"] == "rédaction":
                plain = json.loads(pair["rejected"]["content"])["texte"]
                assert not cp.check_draft(plain, records_in(pair["messages"]), closed).passed
    assert kinds["answer"] > 300 and kinds["abstention"] > 100


def test_reviewed_journal_feeds_training_and_reported_errors_do_not(
    client: TestClient,
    model: ScriptedModel,  # noqa: F811
) -> None:
    cid = conversation(client)
    model.plan(("search_authorisations", {"substance": "ivermectine", "species": "bovins"})).draft("Pas de référence.")
    model.draft("Le registre compte [[liste1:total]] produits pour cette recherche.")
    useful = first(ask(client, cid, "Ivermectine pour les bovins ?"), "done")["message_id"]
    model.plan(("search_authorisations", {"substance": "oxytétracycline"})).draft("[[liste1:total]] produits.")
    wrong = first(ask(client, cid, "Oxytétracycline ?"), "done")["message_id"]
    for mid, rating in ((useful, "utile"), (wrong, "erreur signalée")):
        r = client.post(f"/v1/copilot/messages/{mid}/feedback", headers=PRO, json={"rating": rating})
        assert r.status_code in (200, 201), r.text

    sft, dpo, stats = journal.examples()
    assert stats["messages_utiles"] == 1 and stats["signales_en_revue"] == 1
    assert {e["scenario"] for e in sft} == {f"journal-{useful}"}
    steps = [e["step"] for e in sft]
    assert steps == ["planification", "planification", "rédaction"]
    plan = sft[0]
    assert plan["messages"][-1]["content"] == "<question>\nIvermectine pour les bovins ?\n</question>"
    assert plan["target"]["tool_calls"] == [
        {"name": "search_authorisations", "arguments": {"substance": "ivermectine", "species": "bovins"}}
    ]
    # Refusée au premier essai, acceptée au second : une vraie paire de préférences.
    (pair,) = dpo
    assert json.loads(pair["rejected"]["content"])["texte"] == "Pas de référence."
    assert "[[liste1:total]]" in pair["chosen"]["content"]
