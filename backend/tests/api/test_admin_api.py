"""Administration : droits par rôle, comptes synchronisés avec l'annuaire, alertes, journal d'audit."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from recallpharma.admin.directory import MemoryDirectory, get_directory

pytestmark = pytest.mark.db

FUNCTIONAL, TECH, AUDITOR, PV, VISITOR = "cpt-09", "cpt-10", "cpt-11", "cpt-08", "cpt-01"


def as_user(user: str) -> dict[str, str]:
    return {"X-RecallPharma-User": user}


@pytest.fixture
def directory(client: TestClient) -> Iterator[MemoryDirectory]:
    memory = MemoryDirectory()
    client.app.dependency_overrides[get_directory] = lambda: memory  # type: ignore[attr-defined]
    yield memory
    client.app.dependency_overrides.clear()  # type: ignore[attr-defined]


def test_admin_space_closed_to_other_roles(client: TestClient) -> None:
    assert client.get("/v1/admin/overview", headers=as_user(VISITOR)).status_code == 403
    for user in (FUNCTIONAL, TECH, AUDITOR, PV):
        assert client.get("/v1/admin/overview", headers=as_user(user)).status_code == 200


def test_overview_counts(client: TestClient) -> None:
    o = client.get("/v1/admin/overview", headers=as_user(FUNCTIONAL)).json()
    assert o["authorisations"]["publiée"] > 0
    assert sum(o["statuses"].values()) == o["authorisations"]["publiée"]
    assert o["alerts_open"]["rouge"] >= 1
    assert o["audit_chain_intact"] is True
    assert set(o["permissions"]) == {"comptes", "alertes"}
    assert client.get("/v1/admin/overview", headers=as_user(AUDITOR)).json()["permissions"] == []


def test_account_lifecycle_is_audited(client: TestClient, directory: MemoryDirectory) -> None:
    body = {"login": "Nouvel.Agent@exemple.fr", "display_name": "Nouvel Agent", "roles": ["Validateur"]}
    assert client.post("/v1/admin/accounts", headers=as_user(AUDITOR), json=body).status_code == 403
    r = client.post("/v1/admin/accounts", headers=as_user(TECH), json=body)
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["login"] == "nouvel.agent@exemple.fr"
    assert len(created["temporary_password"]) >= 12
    assert directory.users["nouvel.agent@exemple.fr"]["roles"] == ["Validateur"]
    assert client.post("/v1/admin/accounts", headers=as_user(TECH), json=body).status_code == 409

    aid = created["id"]
    r = client.put(f"/v1/admin/accounts/{aid}/roles", headers=as_user(FUNCTIONAL), json={"roles": ["Auditeur"]})
    assert r.json()["roles"] == ["Auditeur"]
    assert directory.users["nouvel.agent@exemple.fr"]["roles"] == ["Auditeur"]
    bad = client.put(f"/v1/admin/accounts/{aid}/roles", headers=as_user(FUNCTIONAL), json={"roles": ["Roi"]})
    assert bad.status_code == 422

    r = client.post(f"/v1/admin/accounts/{aid}/active", headers=as_user(FUNCTIONAL), json={"active": False})
    assert r.json()["active"] is False
    assert directory.users["nouvel.agent@exemple.fr"]["enabled"] is False
    r = client.post(f"/v1/admin/accounts/{aid}/password-reset", headers=as_user(TECH))
    assert r.json()["temporary_password"] == directory.users["nouvel.agent@exemple.fr"]["password"]

    actions = [
        e["action"]
        for e in client.get("/v1/admin/audit", headers=as_user(AUDITOR), params={"object_type": "account"}).json()[
            "events"
        ]
    ]
    assert actions[:4] == ["account.password_reset", "account.deactivated", "account.roles_changed", "account.created"]


def test_admin_cannot_lock_themself_out(client: TestClient, directory: MemoryDirectory) -> None:
    r = client.post(f"/v1/admin/accounts/{TECH}/active", headers=as_user(TECH), json={"active": False})
    assert r.status_code == 409
    r = client.put(f"/v1/admin/accounts/{TECH}/roles", headers=as_user(TECH), json={"roles": ["Auditeur"]})
    assert r.status_code == 409


def test_alert_publish_and_close(client: TestClient) -> None:
    body = {
        "type": "rappel de lot",
        "level": "rouge",
        "jurisdictions": ["PA"],
        "authorisation_ids": ["amm-001"],
        "batch_numbers": ["L99-0001"],
        "text": "Rappel du lot L99-0001 de Produit-001 (alerte fictive de test).",
    }
    assert client.post("/v1/admin/alerts", headers=as_user(AUDITOR), json=body).status_code == 403
    r = client.post("/v1/admin/alerts", headers=as_user(PV), json=body)
    assert r.status_code == 201, r.text
    alert = r.json()
    assert alert["published_at"] == "2027-09-07"
    public = {a["id"] for a in client.get("/v1/alerts").json()}
    assert alert["id"] in public
    sheet = client.get("/v1/authorisations/amm-001", params={"as_of": "2027-09-07"}).json()
    assert any(a["id"] == alert["id"] for a in sheet["alerts"])

    r = client.post(
        f"/v1/admin/alerts/{alert['id']}/close", headers=as_user(FUNCTIONAL), json={"reason": "Lot retrouvé conforme"}
    )
    assert r.json()["closed_at"] == "2027-09-07"
    again = client.post(f"/v1/admin/alerts/{alert['id']}/close", headers=as_user(FUNCTIONAL), json={"reason": "encore"})
    assert again.status_code == 409
    bad = dict(body, jurisdictions=["ZZ"])
    assert client.post("/v1/admin/alerts", headers=as_user(PV), json=bad).status_code == 422


def test_authorisations_include_unpublished(client: TestClient) -> None:
    rows = client.get("/v1/admin/authorisations", headers=as_user(AUDITOR)).json()
    states = {r["publication_state"] for r in rows}
    assert "publiée" in states and len(states) > 1
    assert all(r["status"] is None for r in rows if r["publication_state"] != "publiée")
    pa = client.get(
        "/v1/admin/authorisations", headers=as_user(AUDITOR), params={"jurisdiction": "PA", "q": "produit-001"}
    ).json()
    assert pa and all(r["jurisdiction"] == "PA" for r in pa)


def test_audit_pagination(client: TestClient) -> None:
    first = client.get("/v1/admin/audit", headers=as_user(AUDITOR), params={"limit": 2}).json()
    assert len(first["events"]) == 2
    if first["next_before"] is not None:
        second = client.get(
            "/v1/admin/audit", headers=as_user(AUDITOR), params={"limit": 2, "before": first["next_before"]}
        ).json()
        assert second["events"][0]["seq"] < first["events"][-1]["seq"]
