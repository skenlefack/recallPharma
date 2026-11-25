"""Double authentification : inscription, vérification, anti-rejeu, verrouillage, désactivation, réinitialisation."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from recallpharma.domain import totp

pytestmark = pytest.mark.db

USER, ADMIN = "cpt-03", "cpt-09"


def as_user(user: str) -> dict[str, str]:
    return {"X-RecallPharma-User": user}


def test_enrol_verify_and_disable(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    assert client.get("/v1/me", headers=as_user(USER)).json()["mfa_enabled"] is False
    assert client.post("/v1/me/mfa/verify", headers=as_user(USER), json={"code": "000000"}).status_code == 409

    setup = client.post("/v1/me/mfa/setup", headers=as_user(USER)).json()
    secret = setup["secret"]
    assert setup["otpauth_uri"].startswith("otpauth://totp/RecallPharma")
    assert client.post("/v1/me/mfa/activate", headers=as_user(USER), json={"code": "000000"}).status_code == 401
    code = totp.code_at(secret, time.time())
    r = client.post("/v1/me/mfa/activate", headers=as_user(USER), json={"code": code})
    assert r.status_code == 200 and r.json()["enabled"] is True
    assert client.get("/v1/me", headers=as_user(USER)).json()["mfa_enabled"] is True
    assert client.post("/v1/me/mfa/setup", headers=as_user(USER)).status_code == 409

    # Le même code ne sert pas deux fois ; le code du pas suivant passe.
    assert client.post("/v1/me/mfa/verify", headers=as_user(USER), json={"code": code}).status_code == 401
    following = totp.code_at(secret, time.time() + 30)
    assert client.post("/v1/me/mfa/verify", headers=as_user(USER), json={"code": following}).status_code == 200

    rows = {a["id"]: a for a in client.get("/v1/admin/accounts", headers=as_user(ADMIN)).json()}
    assert rows[USER]["mfa_enabled"] is True

    # Le secret n'est jamais stocké en clair.
    from recallpharma.db.session import session_factory

    with session_factory()() as s:
        stored = s.execute(text("SELECT secret FROM core.account_mfa WHERE account_id = :a"), {"a": USER}).scalar()
    assert stored and secret not in stored

    # Deux pas plus tard (horloge de l'API avancée), un nouveau code désactive la double authentification.
    later = time.time() + 60
    monkeypatch.setattr("recallpharma.api.mfa.time.time", lambda: later)
    r = client.post("/v1/me/mfa/disable", headers=as_user(USER), json={"code": totp.code_at(secret, later)})
    assert r.json()["enabled"] is False


def test_lock_after_failures_and_admin_reset(client: TestClient) -> None:
    secret = client.post("/v1/me/mfa/setup", headers=as_user(USER)).json()["secret"]
    client.post("/v1/me/mfa/activate", headers=as_user(USER), json={"code": totp.code_at(secret, time.time())})
    for _ in range(5):
        assert client.post("/v1/me/mfa/verify", headers=as_user(USER), json={"code": "000000"}).status_code == 401
    good = totp.code_at(secret, time.time() + 30)
    locked = client.post("/v1/me/mfa/verify", headers=as_user(USER), json={"code": good})
    assert locked.status_code == 429

    assert client.post(f"/v1/admin/accounts/{USER}/mfa-reset", headers=as_user("cpt-11")).status_code == 403
    r = client.post(f"/v1/admin/accounts/{USER}/mfa-reset", headers=as_user(ADMIN))
    assert r.status_code == 200 and r.json()["mfa_enabled"] is False
    assert client.get("/v1/me", headers=as_user(USER)).json()["mfa_enabled"] is False
    actions = [e["action"] for e in client.get("/v1/admin/audit", headers=as_user(ADMIN)).json()["events"]]
    assert {"mfa.locked", "mfa.reset", "mfa.enabled"} <= set(actions)
