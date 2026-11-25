"""Double authentification (TOTP) gérée par l'application : inscription, vérification à la connexion, désactivation.

Keycloak vérifie l'identifiant et le mot de passe ; le BFF n'ouvre la session qu'après `POST /v1/me/mfa/verify` quand
le compte a activé la double authentification. Le secret est chiffré en base (AES-GCM) ; un code ne sert qu'une fois ;
après `mfa_max_failures` échecs, la vérification est bloquée `mfa_lock_minutes` minutes.
"""

from __future__ import annotations

import base64
import hashlib
import os
import time
from datetime import UTC, datetime, timedelta

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import APIRouter
from pydantic import BaseModel, Field

from recallpharma.api.curation import DB, ActorDep
from recallpharma.api.problems import Problem
from recallpharma.config import get_settings
from recallpharma.db import models as m
from recallpharma.db.audit import record
from recallpharma.db.session import session_factory
from recallpharma.domain import totp

router = APIRouter(prefix="/v1/me/mfa", tags=["compte"])


def _key() -> AESGCM:
    return AESGCM(hashlib.sha256(get_settings().mfa_encryption_key.encode()).digest())


def seal(secret: str, account_id: str) -> str:
    nonce = os.urandom(12)
    return base64.b64encode(nonce + _key().encrypt(nonce, secret.encode(), account_id.encode())).decode()


def unseal(sealed: str, account_id: str) -> str:
    raw = base64.b64decode(sealed)
    return _key().decrypt(raw[:12], raw[12:], account_id.encode()).decode()


class MfaStatus(BaseModel):
    enabled: bool
    enabled_at: datetime | None = None


class MfaSetup(BaseModel):
    secret: str  # à saisir dans l'application si le QR code ne peut pas être lu
    otpauth_uri: str


class CodeIn(BaseModel):
    code: str = Field(min_length=6, max_length=8)


def _check(db: DB, row: m.AccountMfa, account_id: str, code: str) -> None:
    """Vérifie le code ; compte les échecs et verrouille au-delà du seuil."""
    s = get_settings()
    now = datetime.now(UTC)
    if row.locked_until and row.locked_until > now:
        minutes = max(1, int((row.locked_until - now).total_seconds() // 60) + 1)
        raise Problem(429, "mfa_locked", f"Trop d'essais : réessayer dans {minutes} min")
    step = totp.verify(unseal(row.secret, account_id), code, time.time(), row.last_step)
    if step is None:
        # Transaction à part : la requête échoue (et sa transaction est annulée), le compteur d'échecs doit rester.
        with session_factory()() as other, other.begin():
            failed = other.get(m.AccountMfa, account_id, with_for_update=True)
            assert failed is not None
            failed.failed_attempts += 1
            if failed.failed_attempts >= s.mfa_max_failures:
                failed.locked_until = now + timedelta(minutes=s.mfa_lock_minutes)
                failed.failed_attempts = 0
                record(other, actor=account_id, action="mfa.locked", object_type="account", object_id=account_id)
        raise Problem(401, "mfa_invalid", "Code incorrect ou expiré")
    row.last_step, row.failed_attempts, row.locked_until = step, 0, None


@router.get("", response_model=MfaStatus)
def status(db: DB, actor: ActorDep) -> MfaStatus:
    row = db.get(m.AccountMfa, actor.id)
    return MfaStatus(enabled=bool(row and row.enabled_at), enabled_at=row.enabled_at if row else None)


@router.post("/setup", response_model=MfaSetup)
def setup(db: DB, actor: ActorDep) -> MfaSetup:
    row = db.get(m.AccountMfa, actor.id)
    if row and row.enabled_at:
        raise Problem(409, "mfa_enabled", "Double authentification déjà active : la désactiver d'abord")
    secret = totp.new_secret()
    if row is None:
        row = m.AccountMfa(account_id=actor.id, secret=seal(secret, actor.id))
        db.add(row)
    else:
        row.secret, row.last_step, row.failed_attempts, row.locked_until = seal(secret, actor.id), None, 0, None
    account = db.get(m.Account, actor.id)
    assert account is not None
    return MfaSetup(secret=secret, otpauth_uri=totp.provisioning_uri(secret, account.login))


@router.post("/activate", response_model=MfaStatus)
def activate(db: DB, actor: ActorDep, body: CodeIn) -> MfaStatus:
    row = db.get(m.AccountMfa, actor.id)
    if row is None or row.enabled_at:
        raise Problem(409, "mfa_no_setup", "Aucune inscription en cours")
    _check(db, row, actor.id, body.code)
    row.enabled_at = datetime.now(UTC)
    record(db, actor=actor.id, action="mfa.enabled", object_type="account", object_id=actor.id)
    return MfaStatus(enabled=True, enabled_at=row.enabled_at)


@router.post("/verify", response_model=MfaStatus)
def verify(db: DB, actor: ActorDep, body: CodeIn) -> MfaStatus:
    row = db.get(m.AccountMfa, actor.id)
    if row is None or row.enabled_at is None:
        raise Problem(409, "mfa_disabled", "Double authentification non activée")
    _check(db, row, actor.id, body.code)
    return MfaStatus(enabled=True, enabled_at=row.enabled_at)


@router.post("/disable", response_model=MfaStatus)
def disable(db: DB, actor: ActorDep, body: CodeIn) -> MfaStatus:
    row = db.get(m.AccountMfa, actor.id)
    if row is None or row.enabled_at is None:
        raise Problem(409, "mfa_disabled", "Double authentification non activée")
    _check(db, row, actor.id, body.code)
    db.delete(row)
    record(db, actor=actor.id, action="mfa.disabled", object_type="account", object_id=actor.id)
    return MfaStatus(enabled=False)
