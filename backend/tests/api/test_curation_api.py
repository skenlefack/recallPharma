"""Circuit de validation de bout en bout sur PostgreSQL (CT-ING-01/02, CT-VAL-01 à CT-VAL-04).

Comptes du jeu A10 : A = cpt-06 (validateur), B = cpt-13 (validateur), C = cpt-07 (responsable réglementaire),
arbitre = cpt-15 (second responsable réglementaire), administrateur technique = cpt-10.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.db

A, B, C, ARBITER, TECH = "cpt-06", "cpt-13", "cpt-07", "cpt-15", "cpt-10"
CRITICAL = [
    "denomination", "ma_number", "jurisdiction", "events", "holder", "components", "pharmaceutical_form",
    "routes", "target_species", "posology", "withdrawal_periods", "prohibitions", "contraindications",
    "dispensing_condition",
]  # fmt: skip


def as_user(user: str) -> dict[str, str]:
    return {"X-RecallPharma-User": user}


def upload(client: TestClient, content: bytes, title: str = "Décision d'AMM (SPÉCIMEN)", **extra: Any) -> Any:
    return client.post(
        "/v1/curation/documents",
        headers=as_user(A),
        files={"file": ("decision.pdf", content, "application/pdf")},
        data={"title": title, "nature": "officielle", "document_date": "2027-08-20", **extra},
    )


def new_payload() -> dict[str, Any]:
    return {
        "jurisdiction": "PA",
        "ma_number": "PA-V-2027-0100",
        "holder": "Laboratoires Alpha (fictif)",
        "manufacturer": "Beta Santé Animale (fictif)",
        "dispensing_condition": "sur ordonnance vétérinaire",
        "grant_date": "2027-08-15",
        "events": [{"type": "octroi", "decision_date": "2027-08-15", "effective_date": "2027-08-15"}],
        "product": {
            "name": "Produit-100",
            "designation": "florfénicol 300 mg/mL, solution injectable",
            "pharmaceutical_form": "solution injectable",
            "routes": ["IM"],
            "target_species": ["bovins"],
            "components": [
                {
                    "substance_id": "sub-10",
                    "strength_as_stated": "300 mg/mL",
                    "strength_value": "300",
                    "strength_unit": "mg",
                    "strength_basis": "par mL",
                }
            ],
        },
        "spc": {
            "languages": ["fr"],
            "posology": "20 mg/kg en IM, deux injections à 48 h d'intervalle",
            "contraindications": ["Ne pas utiliser chez les taureaux reproducteurs adultes."],
            "restrictions": [],
            "withdrawal_periods": [
                {
                    "species": "bovins",
                    "commodity": "viande et abats",
                    "route": "IM",
                    "kind": "valeur",
                    "value": "30",
                    "unit": "jour",
                },
                {"species": "bovins", "commodity": "lait", "route": "IM", "kind": "interdit"},
            ],
        },
    }


def blind_from(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "ma_number": payload["ma_number"],
        "components": [
            {"substance_id": x["substance_id"], "strength_as_stated": x["strength_as_stated"]}
            for x in payload["product"]["components"]
        ],
        "posology": payload["spc"]["posology"],
        "withdrawal_periods": payload["spc"]["withdrawal_periods"],
    }


def provenance(document_id: int) -> dict[str, Any]:
    return {
        f: {"document_id": document_id, "page": 1 if f in ("ma_number", "holder", "events") else 3} for f in CRITICAL
    }


def view_all(client: TestClient, proposal_id: int, user: str) -> None:
    for f in CRITICAL:
        r = client.post(f"/v1/curation/proposals/{proposal_id}/fields/{f}/source-view", headers=as_user(user))
        assert r.status_code == 200, r.json()


def first_validate(client: TestClient, proposal_id: int, user: str = B) -> Any:
    return client.post(
        f"/v1/curation/proposals/{proposal_id}/first-validation",
        headers=as_user(user),
        json={"approve": True, "confirmed_fields": CRITICAL},
    )


@pytest.fixture(scope="module")
def document_id(client: TestClient) -> int:
    r = upload(client, b"%PDF-1.7 decision fictive")
    assert r.status_code == 201
    return int(r.json()["id"])


def test_document_capture_ct_ing_01_02(client: TestClient, document_id: int) -> None:
    assert upload(client, b"%PDF-1.7 decision fictive").status_code == 409  # même empreinte
    v2 = upload(client, b"%PDF-1.7 decision fictive corrigee", replaces_document_id=str(document_id))
    assert v2.status_code == 201 and v2.json()["replaces_document_id"] == document_id
    tech = client.post(
        "/v1/curation/documents",
        headers=as_user(TECH),
        files={"file": ("x.pdf", b"autre", "application/pdf")},
        data={"title": "x", "nature": "officielle", "document_date": "2027-08-20"},
    )
    assert tech.status_code == 403


def test_new_authorisation_full_circuit_ct_val_01_02(client: TestClient, document_id: int) -> None:
    payload = new_payload()
    r = client.post("/v1/curation/proposals", headers=as_user(A), json={"payload": payload, "provenance": {}})
    assert r.status_code == 201
    pid = r.json()["id"]
    assert {i["code"] for i in r.json()["issues"]} == {"no_source"}

    assert client.post(f"/v1/curation/proposals/{pid}/submit", headers=as_user(A)).status_code == 422
    r = client.put(
        f"/v1/curation/proposals/{pid}",
        headers=as_user(A),
        json={"payload": payload, "provenance": provenance(document_id), "expected_revision": 1},
    )
    assert r.status_code == 200 and r.json()["issues"] == []
    stale = client.put(
        f"/v1/curation/proposals/{pid}",
        headers=as_user(A),
        json={"payload": payload, "provenance": provenance(document_id), "expected_revision": 1},
    )
    assert stale.status_code == 409
    assert (
        client.post(f"/v1/curation/proposals/{pid}/submit", headers=as_user(A)).json()["state"]
        == "en première validation"
    )

    # CT-VAL-01 : pas de confirmation sans avoir affiché la page source
    refused = first_validate(client, pid)
    assert refused.status_code == 422 and refused.json()["title"].startswith("Confirmation refusée")
    assert first_validate(client, pid, A).status_code == 403  # RG-32
    assert first_validate(client, pid, TECH).status_code == 403
    view_all(client, pid, B)
    assert first_validate(client, pid).json()["state"] == "en seconde validation"

    # Le second validateur ne voit pas les valeurs qu'il doit ressaisir
    form = client.get(f"/v1/curation/proposals/{pid}/blind-entry", headers=as_user(C)).json()
    assert form["payload"]["ma_number"] is None and form["payload"]["spc"]["withdrawal_periods"] is None
    assert client.get(f"/v1/curation/proposals/{pid}", headers=as_user(C)).json()["payload"]["ma_number"] is None

    blind = blind_from(payload)
    for user in (A, B):  # CT-VAL-02
        assert (
            client.post(f"/v1/curation/proposals/{pid}/blind-entry", headers=as_user(user), json=blind).status_code
            == 403
        )
    assert client.get("/v1/search", params={"q": "PA-V-2027-0100"}).json()["hits"] == []  # invisible avant C

    blind["ma_number"] = "pa-v-2027-0100"
    blind["components"][0]["strength_as_stated"] = "300 mg/ml"
    published = client.post(f"/v1/curation/proposals/{pid}/blind-entry", headers=as_user(C), json=blind).json()
    assert published["state"] == "publiée"
    ma_id = published["authorisation_id"]

    sheet = client.get(f"/v1/authorisations/{ma_id}").json()
    assert sheet["assessment"]["status"] == "valide"
    assert sheet["assessment"]["evidence"]["level"] == "A"
    assert sheet["regulation"]["validations"] == 2
    assert sheet["spc"]["posology"] == payload["spc"]["posology"]
    assert client.get("/v1/search", params={"q": "PA-V-2027-0100"}).json()["hits"][0]["authorisation_id"] == ma_id

    # Le numéro est désormais pris : un doublon est refusé à la soumission (RG-01)
    dup = client.post(
        "/v1/curation/proposals", headers=as_user(A), json={"payload": payload, "provenance": provenance(document_id)}
    ).json()
    r = client.post(f"/v1/curation/proposals/{dup['id']}/submit", headers=as_user(A))
    assert r.status_code == 422 and "RG-01" in r.json()["title"]


def test_dispute_and_arbitration_ct_val_03_04(client: TestClient, document_id: int) -> None:
    r = client.post("/v1/curation/authorisations/amm-001/proposals", headers=as_user(A))
    assert r.status_code == 201
    proposal = r.json()
    pid = proposal["id"]
    payload = copy.deepcopy(proposal["payload"])
    payload["spc"]["posology"] = "10 mg/kg en IM pendant 3 jours"
    original = payload["spc"]["withdrawal_periods"][0]["value"]
    payload["spc"]["withdrawal_periods"][0]["value"] = "35"
    r = client.put(
        f"/v1/curation/proposals/{pid}",
        headers=as_user(A),
        json={"payload": payload, "provenance": provenance(document_id), "expected_revision": proposal["revision"]},
    )
    assert r.status_code == 200
    assert client.post(f"/v1/curation/proposals/{pid}/submit", headers=as_user(A)).status_code == 200

    history = client.get(f"/v1/curation/proposals/{pid}/history", headers=as_user(A)).json()
    corrections = {c["field"] for c in history[1]["detail"]["corrections"]}  # CT-VAL-04
    assert {"posology", "withdrawal_periods"} <= corrections

    view_all(client, pid, B)
    assert first_validate(client, pid).status_code == 200

    blind = blind_from(payload)
    blind["withdrawal_periods"][0]["value"] = original  # C lit l'ancienne valeur : désaccord
    disputed = client.post(f"/v1/curation/proposals/{pid}/blind-entry", headers=as_user(C), json=blind).json()
    assert disputed["state"] == "en litige"
    assert [d["field"] for d in disputed["discrepancies"]] == ["withdrawal_periods"]

    # RG-11 : la version publiée reste visible, « en cours de vérification »
    sheet = client.get("/v1/authorisations/amm-001").json()
    assert any(b["rule"] == "RG-11" for b in sheet["assessment"]["banners"])
    assert sheet["spc"]["withdrawal_periods"][0]["value"] == original

    arbitration = {"decision": "retenir la ressaisie", "reason": "RCP p. 3 : délai de 28 jours pour la viande"}
    assert (
        client.post(f"/v1/curation/proposals/{pid}/arbitration", headers=as_user(C), json=arbitration).status_code
        == 403
    )
    assert (
        client.post(
            f"/v1/curation/proposals/{pid}/arbitration", headers=as_user(ARBITER), json={**arbitration, "reason": ""}
        ).status_code
        == 422
    )
    done = client.post(f"/v1/curation/proposals/{pid}/arbitration", headers=as_user(ARBITER), json=arbitration).json()
    assert done["state"] == "publiée" and done["arbitration_reason"] == arbitration["reason"]

    sheet = client.get("/v1/authorisations/amm-001").json()
    assert not any(b["rule"] == "RG-11" for b in sheet["assessment"]["banners"])
    assert float(sheet["spc"]["withdrawal_periods"][0]["value"]) == float(original)
    assert sheet["spc"]["version_label"] == "v2"  # l'ancien RCP reste en base (v1)
    last = client.get(f"/v1/curation/proposals/{pid}/history", headers=as_user(A)).json()[-1]
    assert last["action"] == "arbitrage" and last["detail"]["reason"] == arbitration["reason"]


def test_edit_after_signature_resets_review(client: TestClient, document_id: int) -> None:
    payload = new_payload()
    payload["ma_number"] = "PA-V-2027-0200"
    pid = client.post(
        "/v1/curation/proposals", headers=as_user(A), json={"payload": payload, "provenance": provenance(document_id)}
    ).json()["id"]
    client.post(f"/v1/curation/proposals/{pid}/submit", headers=as_user(A))
    view_all(client, pid, B)
    assert first_validate(client, pid).json()["first_validator"] == B
    payload["holder"] = "Gamma Vet (fictif)"
    r = client.put(
        f"/v1/curation/proposals/{pid}",
        headers=as_user(A),
        json={"payload": payload, "provenance": provenance(document_id), "expected_revision": 1},
    ).json()
    assert r["state"] == "proposée" and r["first_validator"] is None
    client.post(f"/v1/curation/proposals/{pid}/submit", headers=as_user(A))
    refused = first_validate(client, pid)  # pages vues à la révision précédente : à revoir
    assert refused.status_code == 422


def test_ambiguous_strength_cannot_be_submitted_rg_07(client: TestClient, document_id: int) -> None:
    payload = new_payload()
    payload["ma_number"] = "PA-V-2027-0300"
    payload["product"]["components"][0] |= {
        "strength_as_stated": "10 %",
        "strength_value": None,
        "strength_unit": None,
        "strength_basis": None,
    }
    pid = client.post(
        "/v1/curation/proposals", headers=as_user(A), json={"payload": payload, "provenance": provenance(document_id)}
    ).json()["id"]
    r = client.post(f"/v1/curation/proposals/{pid}/submit", headers=as_user(A))
    assert r.status_code == 422 and "sans base déclarée" in r.json()["title"]


def test_audit_chain_intact_after_workflow(client: TestClient) -> None:
    from recallpharma.db.audit import verify_chain
    from recallpharma.db.session import session_factory

    with session_factory()() as session:
        assert verify_chain(session) is None
