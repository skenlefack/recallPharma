"""Authentification : jeton d'accès OIDC (Keycloak) vérifié par l'API, rôles du domaine tirés du jeton (ADR-09)."""

from __future__ import annotations

import time
import uuid
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
    scheme, _, token = (authorization or "").partition(" ")
    bearer = token if scheme.lower() == "bearer" and token else None
    if bearer and _is_delegated(bearer):
        raise delegated_forbidden()  # le jeton de la passerelle ne sert qu'aux outils de lecture, dans tous les modes
    if get_settings().auth_mode == "dev":
        if not x_recallpharma_user:
            raise _unauthorized("En-tête X-RecallPharma-User manquant (mode dev)")
        return Identity(account_id=x_recallpharma_user)
    if not bearer:
        raise _unauthorized("Jeton Bearer manquant")
    return identity_from_claims(verify_token(bearer))


IdentityDep = Annotated[Identity, Depends(current_identity)]


# --- Jeton délégué du Copilot (ADR-08) -----------------------------------------------------------
# Sujet : l'utilisateur ; acteur : passerelle-ia ; audience : api-copilot-lecture ; portée : registre:lire ; 5 minutes.
# La passerelle ne reçoit jamais le jeton de l'utilisateur. Prototype : émis et signé par l'API (HS256) ; l'échange de
# jeton RFC 8693 de Keycloak le remplacera sans changer les points d'accès.

DELEGATED_TTL_S = 300


def delegated_forbidden() -> Problem:
    return Problem(403, "delegated_token_forbidden", "Jeton délégué refusé hors des outils du Copilot")


class Delegation:
    def __init__(self, account_id: str, conversation_id: str | None) -> None:
        self.account_id, self.conversation_id = account_id, conversation_id


def mint_delegated(account_id: str, conversation_id: str | None) -> str:
    s = get_settings()
    now = int(time.time())
    claims = {
        "iss": "recallpharma-api",
        "sub": account_id,
        "act": {"sub": "passerelle-ia"},
        "aud": s.copilot_token_audience,
        "scope": "registre:lire",
        "cid": conversation_id,
        "iat": now,
        "exp": now + DELEGATED_TTL_S,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(claims, s.copilot_token_secret, algorithm="HS256")


def _is_delegated(token: str) -> bool:
    try:
        return bool(jwt.get_unverified_header(token).get("alg") == "HS256")
    except jwt.PyJWTError:
        return False


def delegated_reader(authorization: Annotated[str | None, Header()] = None) -> Delegation:
    """Seule identité acceptée par les outils du Copilot : le jeton délégué, en lecture."""
    s = get_settings()
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized("Jeton délégué manquant")
    try:
        claims = jwt.decode(
            token,
            s.copilot_token_secret,
            algorithms=["HS256"],
            audience=s.copilot_token_audience,
            issuer="recallpharma-api",
            options={"require": ["exp", "sub", "aud", "act"]},
        )
    except jwt.PyJWTError as exc:
        raise _unauthorized("Jeton délégué expiré ou invalide") from exc
    if claims.get("scope") != "registre:lire" or claims.get("act", {}).get("sub") != "passerelle-ia":
        raise Problem(403, "insufficient_scope", "Portée insuffisante")
    return Delegation(str(claims["sub"]), claims.get("cid"))


DelegationDep = Annotated[Delegation, Depends(delegated_reader)]
