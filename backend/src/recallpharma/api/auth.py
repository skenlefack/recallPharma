"""Authentification : jeton d'accès OIDC (Keycloak) vérifié par l'API, rôles du domaine tirés du jeton (ADR-09)."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Any

import jwt
from fastapi import Depends, Header

from recallpharma.api.problems import Problem
from recallpharma.config import get_settings

#: Rôles de royaume Keycloak → rôles du domaine. Un rôle inconnu du jeton est ignoré.
ROLE_SLUGS = {
    "visiteur": "Visiteur",
    "inscrit": "Inscrit",
    "professionnel-verifie": "Professionnel vérifié",
    "titulaire": "Titulaire",
    "agent-autorite": "Agent d'autorité",
    "validateur": "Validateur",
    "responsable-reglementaire": "Responsable réglementaire",
    "responsable-produit": "Responsable produit",
    "evaluateur-pharmacovigilance": "Évaluateur de pharmacovigilance",
    "administrateur-fonctionnel": "Administrateur fonctionnel",
    "administrateur-technique": "Administrateur technique",
    "auditeur": "Auditeur",
    "application-partenaire": "Application partenaire",
}


class Identity:
    """Qui appelle : identifiant de connexion et rôles, ou compte désigné directement (mode « dev »)."""

    def __init__(self, *, login: str | None = None, account_id: str | None = None, roles: frozenset[str] = frozenset()):
        self.login, self.account_id, self.roles = login, account_id, roles


def _unauthorized(detail: str) -> Problem:
    return Problem(401, "unauthenticated", "Authentification requise", detail)


@lru_cache
def _jwks(url: str) -> jwt.PyJWKClient:
    return jwt.PyJWKClient(url, cache_keys=True, lifespan=300, timeout=5)


def verify_token(token: str) -> dict[str, Any]:
    s = get_settings()
    try:
        key = _jwks(s.oidc_jwks_url or f"{s.oidc_issuer}/protocol/openid-connect/certs").get_signing_key_from_jwt(token)
        claims: dict[str, Any] = jwt.decode(
            token,
            key.key,
            algorithms=["RS256", "ES256", "PS256"],
            audience=s.oidc_audience,
            issuer=s.oidc_issuer,
            options={"require": ["exp", "iat", "sub", "iss", "aud"]},
            leeway=30,
        )
    except jwt.PyJWKClientConnectionError as exc:
        raise Problem(503, "idp_unavailable", "Fournisseur d'identité injoignable") from exc
    except jwt.PyJWTError as exc:
        raise _unauthorized("Jeton absent, expiré ou invalide") from exc
    return claims


def identity_from_claims(claims: dict[str, Any]) -> Identity:
    login = claims.get("preferred_username") or claims.get("email")
    if not login:
        raise _unauthorized("Le jeton ne désigne aucun utilisateur")
    realm_roles = claims.get("realm_access", {}).get("roles", [])
    return Identity(login=str(login), roles=frozenset(ROLE_SLUGS[r] for r in realm_roles if r in ROLE_SLUGS))


def current_identity(
    authorization: Annotated[str | None, Header()] = None,
    x_recallpharma_user: Annotated[str | None, Header()] = None,
) -> Identity:
    if get_settings().auth_mode == "dev":
        if not x_recallpharma_user:
            raise _unauthorized("En-tête X-RecallPharma-User manquant (mode dev)")
        return Identity(account_id=x_recallpharma_user)
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized("Jeton Bearer manquant")
    return identity_from_claims(verify_token(token))


IdentityDep = Annotated[Identity, Depends(current_identity)]
