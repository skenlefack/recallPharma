"""Annuaire des comptes (Keycloak) : création, rôles, activation, mot de passe provisoire.

Keycloak reste la source d'identité ; l'API le pilote par son API d'administration avec un compte de service
(`recallpharma-admin`, rôles manage-users et view-users du royaume).
Les tests remplacent l'annuaire par `MemoryDirectory`.
"""

from __future__ import annotations

import secrets
import string
from typing import Protocol

import httpx

from recallpharma.api.auth import ROLE_SLUGS
from recallpharma.config import get_settings

SLUG_OF = {label: slug for slug, label in ROLE_SLUGS.items()}


class DirectoryError(Exception):
    """L'annuaire a refusé l'opération (compte existant, inconnu, indisponible)."""


def temporary_password() -> str:
    """Mot de passe provisoire de 16 caractères (politique du royaume : 12 au moins), à changer par l'utilisateur."""
    alphabet = string.ascii_letters + string.digits
    return (
        "".join(secrets.choice(alphabet) for _ in range(14)) + secrets.choice("!#%+-") + secrets.choice(string.digits)
    )


class Directory(Protocol):
    def create_user(self, login: str, display_name: str, roles: list[str], password: str) -> None: ...
    def set_roles(self, login: str, roles: list[str]) -> None: ...
    def set_enabled(self, login: str, enabled: bool) -> None: ...
    def reset_password(self, login: str, password: str) -> None: ...


class KeycloakDirectory:
    def __init__(self) -> None:
        s = get_settings()
        self.base = s.keycloak_admin_url.rstrip("/")
        self.realm = s.keycloak_realm
        self.client_id = s.keycloak_admin_client_id
        self.client_secret = s.keycloak_admin_client_secret

    def _client(self) -> httpx.Client:
        try:
            token = httpx.post(
                f"{self.base}/realms/{self.realm}/protocol/openid-connect/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                timeout=10,
            )
            token.raise_for_status()
        except httpx.HTTPError as exc:
            raise DirectoryError("Annuaire Keycloak indisponible") from exc
        return httpx.Client(
            base_url=f"{self.base}/admin/realms/{self.realm}",
            headers={"Authorization": f"Bearer {token.json()['access_token']}"},
            timeout=10,
        )

    @staticmethod
    def _user_id(http: httpx.Client, login: str) -> str:
        found = http.get("/users", params={"username": login, "exact": "true"}).json()
        if not found:
            raise DirectoryError("Compte absent de l'annuaire")
        return str(found[0]["id"])

    def _roles(self, http: httpx.Client, labels: list[str]) -> list[dict[str, str]]:
        out = []
        for label in labels:
            r = http.get(f"/roles/{SLUG_OF[label]}")
            r.raise_for_status()
            out.append(r.json())
        return out

    def create_user(self, login: str, display_name: str, roles: list[str], password: str) -> None:
        with self._client() as http:
            first, _, last = display_name.partition(" ")
            r = http.post(
                "/users",
                json={
                    "username": login,
                    "email": login,
                    "emailVerified": True,
                    "enabled": True,
                    "firstName": first,
                    "lastName": last or first,
                    "credentials": [{"type": "password", "value": password, "temporary": False}],
                },
            )
            if r.status_code == 409:
                raise DirectoryError("Un compte existe déjà avec cette adresse")
            r.raise_for_status()
            uid = self._user_id(http, login)
            http.post(f"/users/{uid}/role-mappings/realm", json=self._roles(http, roles)).raise_for_status()

    def set_roles(self, login: str, roles: list[str]) -> None:
        with self._client() as http:
            uid = self._user_id(http, login)
            current = [r for r in http.get(f"/users/{uid}/role-mappings/realm").json() if r["name"] in ROLE_SLUGS]
            if current:
                http.request("DELETE", f"/users/{uid}/role-mappings/realm", json=current).raise_for_status()
            if roles:
                http.post(f"/users/{uid}/role-mappings/realm", json=self._roles(http, roles)).raise_for_status()

    def set_enabled(self, login: str, enabled: bool) -> None:
        with self._client() as http:
            uid = self._user_id(http, login)
            http.put(f"/users/{uid}", json={"enabled": enabled}).raise_for_status()
            if not enabled:
                http.post(f"/users/{uid}/logout").raise_for_status()  # ferme les sessions ouvertes

    def reset_password(self, login: str, password: str) -> None:
        with self._client() as http:
            uid = self._user_id(http, login)
            http.put(
                f"/users/{uid}/reset-password", json={"type": "password", "value": password, "temporary": False}
            ).raise_for_status()


class MemoryDirectory:
    """Annuaire en mémoire pour les tests."""

    def __init__(self) -> None:
        self.users: dict[str, dict[str, object]] = {}

    def create_user(self, login: str, display_name: str, roles: list[str], password: str) -> None:
        if login in self.users:
            raise DirectoryError("Un compte existe déjà avec cette adresse")
        self.users[login] = {"name": display_name, "roles": list(roles), "enabled": True, "password": password}

    def _get(self, login: str) -> dict[str, object]:
        return self.users.setdefault(login, {"roles": [], "enabled": True})

    def set_roles(self, login: str, roles: list[str]) -> None:
        self._get(login)["roles"] = list(roles)

    def set_enabled(self, login: str, enabled: bool) -> None:
        self._get(login)["enabled"] = enabled

    def reset_password(self, login: str, password: str) -> None:
        self._get(login)["password"] = password


def get_directory() -> Directory:
    return KeycloakDirectory()
