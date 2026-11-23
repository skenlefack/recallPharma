"""Tests de l'API sur une vraie base PostgreSQL chargée avec le jeu A10 (CT-REG-01, CT-REG-02, CT-ALR-03)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

pytestmark = pytest.mark.db

AS_OF = {"as_of": "2027-09-07"}


def test_search_tolerates_accents_and_typos(client: TestClient) -> None:
    exact = client.get("/v1/search", params={"q": "oxytétracycline", **AS_OF}).json()
    assert exact["hits"]
    no_accent = client.get("/v1/search", params={"q": "oxytetracycline", **AS_OF}).json()
    assert {h["authorisation_id"] for h in no_accent["hits"]} == {h["authorisation_id"] for h in exact["hits"]}
    typo = client.get("/v1/search", params={"q": "oxytetracyline", **AS_OF}).json()
    assert typo["hits"]


def test_search_by_ma_number(client: TestClient) -> None:
    hits = client.get("/v1/search", params={"q": "pa v 2023 0002", **AS_OF}).json()["hits"]
    assert hits[0]["authorisation_id"] == "amm-002"


def test_unpublished_never_visible(client: TestClient) -> None:
    assert client.get("/v1/authorisations/amm-024", params=AS_OF).status_code == 404
    hits = client.get("/v1/search", params={"q": "albendazole", **AS_OF}).json()["hits"]
    assert "amm-024" not in {h["authorisation_id"] for h in hits}


def test_suspended_red_banner_ct_reg_01(client: TestClient) -> None:
    sheet = client.get("/v1/authorisations/amm-002", params=AS_OF).json()
    assert sheet["assessment"]["status"] == "suspendue"
    assert sheet["assessment"]["banners"][0]["level"] == "rouge"
    assert "Ne pas délivrer" in sheet["assessment"]["banners"][0]["text"]
    assert any(a["id"] == "alr-001" for a in sheet["alerts"])


def test_bitemporal_sheet(client: TestClient) -> None:
    before = client.get("/v1/authorisations/amm-002", params={"as_of": "2027-07-01"}).json()
    assert before["assessment"]["status"] == "valide"


def test_foreign_authorisation_rg_16_ct_reg_02(client: TestClient) -> None:
    pa_only = client.get("/v1/search", params={"q": "PA-V-2023-0001", **AS_OF}).json()
    assert pa_only["hits"][0]["jurisdiction"] == "PA"
    res = client.get("/v1/search", params={"q": "PA-V-2023-0001", "jurisdiction": "PB", **AS_OF}).json()
    assert res["hits"] and not res["hits"][0]["applies_to_requested"]
    assert res["notice"].startswith("Non vérifié comme autorisé dans cette juridiction")


def test_community_authorisation_applies_to_members(client: TestClient) -> None:
    sheet = client.get("/v1/authorisations/amm-049", params=AS_OF).json()
    number = sheet["regulation"]["ma_number"]
    res = client.get("/v1/search", params={"q": number, "jurisdiction": "C1", **AS_OF}).json()
    assert res["hits"][0]["applies_to_requested"] and res["notice"] is None


def test_withdrawal_end_and_ambiguity(client: TestClient) -> None:
    body = {
        "species": "bovins",
        "commodity": "viande et abats",
        "last_administration": "2027-09-07T14:30:00+01:00",
    }
    ambiguous = client.post("/v1/authorisations/amm-002/withdrawal-end", json=body)
    assert ambiguous.status_code == 409
    assert ambiguous.headers["content-type"].startswith("application/problem+json")
    assert len(ambiguous.json()["candidates"]) == 2
    ok = client.post("/v1/authorisations/amm-002/withdrawal-end", json={**body, "route": "IM"}).json()
    assert ok["earliest"].startswith("2027-09-22T00:00:00")  # 14 j → 21/09 14:30 → début du 22
    assert "arrondi au début du jour suivant" in ok["formula"]
    off_label = client.post("/v1/authorisations/amm-002/withdrawal-end", json={**body, "species": "chevaux"})
    assert off_label.status_code == 422 and "Hors AMM" in off_label.json()["title"]
    naive = client.post(
        "/v1/authorisations/amm-002/withdrawal-end",
        json={**body, "route": "IM", "last_administration": "2027-09-07T14:30:00"},
    )
    assert naive.status_code == 422


def test_batch_check_ct_alr_03(client: TestClient) -> None:
    hit = client.post(
        "/v1/batch-check", params=AS_OF, json={"authorisation_id": "amm-001", "batch_number": "L27-0412"}
    ).json()
    assert hit["answer"] == "lot visé par un rappel publié"
    miss = client.post(
        "/v1/batch-check", params=AS_OF, json={"authorisation_id": "amm-001", "batch_number": "X1"}
    ).json()
    assert miss["answer"] == "aucun rappel publié connu"
    assert hit["notice"] == miss["notice"] == "Ne constitue pas une authentification."


def test_alerts_by_jurisdiction(client: TestClient) -> None:
    alerts = client.get("/v1/alerts", params={"jurisdiction": "PB", **AS_OF}).json()
    assert alerts and all("PB" in a["jurisdictions"] for a in alerts)


def test_audit_chain_and_append_only(client: TestClient) -> None:
    from sqlalchemy.exc import DBAPIError

    from recallpharma.db.audit import record, verify_chain
    from recallpharma.db.session import session_factory

    with session_factory()() as session, session.begin():
        record(session, actor="test", action="lecture", object_type="authorisation", object_id="amm-001")
        assert verify_chain(session) is None
    with session_factory()() as session, pytest.raises(DBAPIError, match="Ajout seul"), session.begin():
        session.execute(text("UPDATE integration.audit_event SET actor = 'pirate'"))
    with session_factory()() as session, pytest.raises(DBAPIError, match="Ajout seul"), session.begin():
        session.execute(text("DELETE FROM reg.regulatory_event"))
