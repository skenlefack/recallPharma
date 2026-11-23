"""Journal d'audit chaîné (RG-33) : chaque événement scelle le précédent par SHA-256."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from recallpharma.db.models import AuditEvent

GENESIS = "0" * 64


def canonical(payload: dict[str, Any]) -> bytes:
    """Sérialisation canonique : clés triées, sans espaces, UTF-8 (sous-ensemble de RFC 8785 suffisant
    ici, nos valeurs étant des chaînes, entiers et booléens)."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()


def _digest(prev_hash: str, fields: dict[str, Any]) -> str:
    return hashlib.sha256(prev_hash.encode() + canonical(fields)).hexdigest()


def _fields(e: AuditEvent) -> dict[str, Any]:
    return {
        "actor": e.actor,
        "action": e.action,
        "object_type": e.object_type,
        "object_id": e.object_id,
        "before": e.before,
        "after": e.after,
        "reason": e.reason,
        "created_at": e.created_at.isoformat(),
    }


def record(
    session: Session,
    *,
    actor: str,
    action: str,
    object_type: str,
    object_id: str,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    reason: str | None = None,
) -> AuditEvent:
    # Verrou transactionnel : deux écritures concurrentes ne peuvent pas sceller le même maillon.
    session.execute(text("SELECT pg_advisory_xact_lock(hashtext('integration.audit_event'))"))
    prev = session.scalar(select(AuditEvent.hash).order_by(AuditEvent.seq.desc()).limit(1)) or GENESIS
    event = AuditEvent(
        actor=actor,
        action=action,
        object_type=object_type,
        object_id=object_id,
        before=before,
        after=after,
        reason=reason,
        created_at=datetime.now(UTC),
        prev_hash=prev,
    )
    event.hash = _digest(prev, _fields(event))
    session.add(event)
    session.flush()
    return event


def verify_chain(session: Session) -> int | None:
    """Renvoie le numéro du premier maillon rompu, ou None si la chaîne est intacte."""
    prev = GENESIS
    for e in session.scalars(select(AuditEvent).order_by(AuditEvent.seq)):
        if e.prev_hash != prev or e.hash != _digest(prev, _fields(e)):
            return e.seq
        prev = e.hash
    return None
