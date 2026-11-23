"""Jetons OIDC : signature, émetteur, audience, expiration, rôles recopiés et audités (mode « oidc »)."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import select

from recallpharma.api import auth
from recallpharma.config import get_settings

pytestmark = pytest.mark.db

ISSUER = "http://idp.test/realms/recallpharma"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


class _FakeJwks:
    def get_signing_key_from_jwt(self, token: str) -> Any:
        return jwt.PyJWK.from_dict(
            {**jwt.algorithms.RSAAlgorithm.to_jwk(KEY.public_key(), as_dict=True), "kid": "k1", "alg": "RS256"}
        )


@pytest.fixture
def oidc(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("RECALLPHARMA_AUTH_MODE", "oidc")
    monkeypatch.setenv("RECALLPHARMA_OIDC_ISSUER", ISSUER)
    monkeypatch.setattr(auth, "_jwks", lambda url: _FakeJwks())
    get_settings.cache_clear()
    yield client
    monkeypatch.undo()
    get_settings.cache_clear()


def token(login: str, roles: list[str], *, key: Any = KEY, **overrides: Any) -> dict[str, str]:
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "aud": ["recallpharma-api", "account"],
        "sub": f"sub-{login}",
        "iat": now,
        "exp": now + 300,
        "preferred_username": login,
        "realm_access": {"roles": [*roles, "default-roles-recallpharma"]},
        **overrides,
    }
    return {"Authorization": "Bearer " + jwt.encode(claims, key, algorithm="RS256", headers={"kid": "k1"})}


def test_valid_token_identifies_account_and_roles(oidc: TestClient) -> None:
    r = oidc.get("/v1/me", headers=token("demo06@recallpharma.example", ["validateur"]))
    assert r.status_code == 200, r.text
    assert r.json() == {
        "id": "cpt-06",
        "display_name": "Validateur (cpt-06)",
        "roles": ["Validateur"],
        "can_curate": True,
    }


@pytest.mark.parametrize(
    ("headers", "why"),
    [
        ({}, "absent"),
        ({"Authorization": "Basic abc"}, "mauvais schéma"),
        (token("demo06@recallpharma.example", ["validateur"], key=OTHER_KEY), "signature"),
        (token("demo06@recallpharma.example", ["validateur"], iss="http://autre/realms/x"), "émetteur"),
        (token("demo06@recallpharma.example", ["validateur"], aud="autre-client"), "audience"),
        (token("demo06@recallpharma.example", ["validateur"], exp=int(time.time()) - 120), "expiré"),
        ({"X-RecallPharma-User": "cpt-06"}, "en-tête dev refusé en mode oidc"),
    ],
)
def test_invalid_credentials_are_rejected(oidc: TestClient, headers: dict[str, str], why: str) -> None:
    r = oidc.get("/v1/curation/proposals", headers=headers)
    assert r.status_code == 401, why
    assert r.headers["content-type"].startswith("application/problem+json")


def test_unknown_login_is_rejected(oidc: TestClient) -> None:
    r = oidc.get("/v1/me", headers=token("intrus@example.org", ["validateur"]))
    assert r.status_code == 401


def test_token_roles_prevail_and_change_is_audited(oidc: TestClient) -> None:
    from recallpharma.db import models as m
    from recallpharma.db.session import session_factory

    # Le fournisseur d'identité retire le rôle de validateur : l'API refuse l'écriture et trace le changement.
    headers = token("demo13@recallpharma.example", ["inscrit"])
    me = oidc.get("/v1/me", headers=headers).json()
    assert me["roles"] == ["Inscrit"] and me["can_curate"] is False
    r = oidc.post("/v1/curation/proposals", headers=headers, json={"payload": {}, "provenance": {}})
    assert r.status_code in (403, 422)
    with session_factory()() as s:
        assert s.get(m.Account, "cpt-13").roles == ["Inscrit"]  # type: ignore[union-attr]
        events = s.scalars(
            select(m.AuditEvent).where(
                m.AuditEvent.action == "account.roles_synced", m.AuditEvent.object_id == "cpt-13"
            )
        ).all()
        assert len(events) == 1
    # Rôle rendu : nouvelle trace, pas de doublon tant qu'il ne change pas.
    restore = token("demo13@recallpharma.example", ["validateur"])
    oidc.get("/v1/me", headers=restore)
    oidc.get("/v1/me", headers=restore)
    with session_factory()() as s:
        assert len(s.scalars(select(m.AuditEvent).where(m.AuditEvent.action == "account.roles_synced")).all()) == 2


def test_public_registry_needs_no_token(oidc: TestClient) -> None:
    assert oidc.get("/v1/search", params={"q": "oxytetracycline"}).status_code == 200
