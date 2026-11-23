"""Cas d'usage du circuit de validation : persistance, verrous, historique et journal d'audit (RG-33)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from recallpharma.curation.publication import payload_from_authorisation, publish, removed_events
from recallpharma.db import models as m
from recallpharma.db.audit import record
from recallpharma.domain import curation as c
from recallpharma.domain.identifiers import normalise_ma_number


def actor_for(session: Session, account_id: str) -> c.Actor:
    account = session.get(m.Account, account_id)
    if account is None or not account.active:
        raise c.WorkflowError("unknown_account", "Compte inconnu ou désactivé")
    return c.Actor(account.id, frozenset(account.roles))


def _snapshot(p: m.Proposal) -> c.ProposalSnapshot:
    return c.ProposalSnapshot(c.ProposalState(p.state), p.prepared_by, p.first_validator, p.second_validator)


def _locked(session: Session, proposal_id: int) -> m.Proposal:
    p = session.scalars(select(m.Proposal).where(m.Proposal.id == proposal_id).with_for_update()).one_or_none()
    if p is None:
        raise c.WorkflowError("not_found", "Proposition inconnue")
    return p


def _step(
    session: Session, p: m.Proposal, actor: c.Actor, action: str, before: str, detail: dict[str, Any] | None = None
) -> None:
    session.add(
        m.ProposalStep(
            proposal_id=p.id, actor=actor.id, action=action, from_state=before, to_state=p.state, detail=detail or {}
        )
    )
    record(
        session,
        actor=actor.id,
        action=f"proposition:{action}",
        object_type="proposal",
        object_id=str(p.id),
        before={"state": before},
        after={"state": p.state, "revision": p.revision, **(detail or {})},
        reason=(detail or {}).get("reason"),
    )
    p.updated_at = datetime.now(UTC)
    session.flush()


def _set_dispute(session: Session, p: m.Proposal, value: bool) -> None:
    """RG-11 : pendant le litige, la version publiée reste visible « en cours de vérification »."""
    if p.authorisation_id:
        row = session.get(m.Authorisation, p.authorisation_id)
        if row is not None and row.publication_state == c.ProposalState.PUBLISHED.value:
            row.dispute_open = value


def create(
    session: Session,
    actor: c.Actor,
    payload: dict[str, Any],
    provenance: dict[str, Any],
    authorisation_id: str | None = None,
    origin: str = "saisie",
) -> m.Proposal:
    c.check_prepare(actor)
    if authorisation_id is not None and session.get(m.Authorisation, authorisation_id) is None:
        raise c.WorkflowError("not_found", "AMM inconnue")
    p = m.Proposal(
        authorisation_id=authorisation_id,
        state=c.ProposalState.PROPOSED.value,
        origin=origin,
        payload=payload,
        provenance=provenance,
        prepared_by=actor.id,
        revision=1,
    )
    session.add(p)
    session.flush()
    _step(session, p, actor, "création", c.ProposalState.PROPOSED.value, {"origin": origin})
    return p


def start_update(session: Session, actor: c.Actor, authorisation_id: str) -> m.Proposal:
    """Mise à jour ou revérification d'une AMM publiée : la proposition part de l'état publié ;
    les sources doivent être citées à nouveau."""
    row = session.get(m.Authorisation, authorisation_id)
    if row is None or row.publication_state != c.ProposalState.PUBLISHED.value:
        raise c.WorkflowError("not_found", "AMM inconnue ou non publiée")
    return create(session, actor, payload_from_authorisation(row), {}, authorisation_id, origin="mise à jour")


def edit(
    session: Session,
    actor: c.Actor,
    proposal_id: int,
    payload: dict[str, Any],
    provenance: dict[str, Any],
    expected_revision: int,
) -> m.Proposal:
    p = _locked(session, proposal_id)
    if p.revision != expected_revision:
        raise c.WorkflowError("stale_revision", f"La proposition a changé (révision {p.revision})")
    new_state = c.check_edit(_snapshot(p), actor)
    before_state = p.state
    corrections = [
        {"field": f.key, "proposed": f.read(p.payload), "retained": f.read(payload)}
        for f in c.CRITICAL_FIELDS
        if f.read(p.payload) != f.read(payload)
    ]
    p.payload, p.provenance = payload, provenance
    p.revision += 1
    p.state = new_state.value
    reset = before_state != c.ProposalState.PROPOSED.value
    p.first_validator = p.second_validator = None
    p.blind_entry = p.discrepancies = None
    session.flush()
    _step(session, p, actor, "modification", before_state, {"corrections": corrections, "review_reset": reset})
    return p


def submit(session: Session, actor: c.Actor, proposal_id: int) -> m.Proposal:
    p = _locked(session, proposal_id)
    issues = c.publication_issues(p.payload, p.provenance)
    number = normalise_ma_number(str(p.payload.get("ma_number") or ""))
    duplicate = session.scalar(
        select(func.count())
        .select_from(m.Authorisation)
        .where(
            m.Authorisation.jurisdiction_code == p.payload.get("jurisdiction"),
            m.Authorisation.ma_number_normalized == number,
            m.Authorisation.id != (p.authorisation_id or ""),
        )
    )
    if duplicate:
        issues.append(c.Issue("ma_number", "duplicate", "Une AMM porte déjà ce numéro dans cette juridiction (RG-01)"))
    if p.authorisation_id:
        row = session.get(m.Authorisation, p.authorisation_id)
        if row is not None and removed_events(row, p.payload):
            issues.append(
                c.Issue(
                    "events",
                    "event_removed",
                    "Un événement publié ne se supprime pas : enregistrer un événement compensatoire",
                )
            )
    before = p.state
    p.state = c.check_submit(_snapshot(p), actor, issues).value
    _step(session, p, actor, "soumission", before)
    return p


def view_source(session: Session, actor: c.Actor, proposal_id: int, field: str) -> dict[str, Any]:
    """Affiche la référence source d'un champ et trace la consultation (préalable à sa confirmation)."""
    if field not in c.CRITICAL_KEYS:
        raise c.WorkflowError("unknown_field", f"Champ critique inconnu : {field}")
    p = session.get(m.Proposal, proposal_id)
    if p is None:
        raise c.WorkflowError("not_found", "Proposition inconnue")
    if actor.has(c.Role.TECH_ADMIN) or not actor.has(*c.CURATOR_ROLES):
        raise c.WorkflowError("forbidden", "Rôle de validation requis")
    ref = p.provenance.get(field)
    if not ref:
        raise c.WorkflowError("no_source", "Aucune source citée pour ce champ")
    document = session.get(m.SourceDocument, ref["document_id"])
    if document is None:
        raise c.WorkflowError("no_source", "Document source introuvable")
    session.add(
        m.SourceView(
            proposal_id=p.id,
            revision=p.revision,
            actor=actor.id,
            field=field,
            document_id=document.id,
            page=int(ref["page"]),
        )
    )
    session.flush()
    return {
        "field": field,
        "document_id": document.id,
        "title": document.title,
        "page": int(ref["page"]),
        "zone": ref.get("zone"),
        "sha256": document.sha256,
    }


def first_validation(
    session: Session, actor: c.Actor, proposal_id: int, approve: bool, confirmed: list[str], reason: str | None
) -> m.Proposal:
    p = _locked(session, proposal_id)
    viewed = set(
        session.scalars(
            select(m.SourceView.field).where(
                m.SourceView.proposal_id == p.id,
                m.SourceView.actor == actor.id,
                m.SourceView.revision == p.revision,
            )
        )
    )
    before = p.state
    p.state = c.check_first_validation(_snapshot(p), actor, approve, confirmed, viewed, reason).value
    if approve:
        p.first_validator = actor.id
    _step(session, p, actor, "première validation" if approve else "renvoi", before, {"reason": reason})
    return p


def blind_view(session: Session, actor: c.Actor, proposal_id: int) -> dict[str, Any]:
    p = session.get(m.Proposal, proposal_id)
    if p is None:
        raise c.WorkflowError("not_found", "Proposition inconnue")
    if p.state != c.ProposalState.SECOND_REVIEW.value:
        raise c.WorkflowError("invalid_state", "Aucune ressaisie attendue à cet état")
    if actor.id in (p.prepared_by, p.first_validator):
        raise c.WorkflowError("same_person", "Le second validateur doit être une troisième personne (RG-32)")
    return c.mask_blind_fields(p.payload)


def blind_entry(session: Session, actor: c.Actor, proposal_id: int, blind: dict[str, Any], today: date) -> m.Proposal:
    p = _locked(session, proposal_id)
    discrepancies = c.compare_blind_entry(p.payload, blind)
    before = p.state
    new_state = c.check_blind_entry(_snapshot(p), actor, discrepancies)
    p.second_validator = actor.id
    p.blind_entry = blind
    p.discrepancies = [{"field": d.field, "prepared": d.prepared, "entered": d.entered} for d in discrepancies]
    if new_state is c.ProposalState.PUBLISHED:
        _publish(session, p, today)
    else:
        p.state = new_state.value
        _set_dispute(session, p, True)
    _step(
        session,
        p,
        actor,
        "seconde validation",
        before,
        {"discrepancies": [d.field for d in discrepancies]},
    )
    return p


def arbitrate(
    session: Session,
    actor: c.Actor,
    proposal_id: int,
    decision: c.ArbitrationDecision,
    reason: str | None,
    today: date,
) -> m.Proposal:
    p = _locked(session, proposal_id)
    before = p.state
    new_state = c.check_arbitration(_snapshot(p), actor, decision, reason)
    p.arbiter, p.arbitration_decision, p.arbitration_reason = actor.id, decision.value, reason
    if decision is c.ArbitrationDecision.KEEP_BLIND:
        fields = [d["field"] for d in p.discrepancies or []]
        p.payload = c.apply_blind_values(p.payload, p.blind_entry or {}, fields)
    if new_state is c.ProposalState.PUBLISHED:
        _publish(session, p, today)
    else:
        p.state = new_state.value
        _set_dispute(session, p, False)
    _step(session, p, actor, "arbitrage", before, {"decision": decision.value, "reason": reason})
    return p


def _publish(session: Session, p: m.Proposal, today: date) -> None:
    issues = c.publication_issues(p.payload, p.provenance)
    if issues:  # garde-fou : la soumission a déjà contrôlé, mais un arbitrage a pu changer les valeurs
        raise c.WorkflowError("incomplete", " ; ".join(i.message for i in issues))
    publish(session, p, today)
    p.state = c.ProposalState.PUBLISHED.value
    session.flush()
