"""Back-office de validation : propositions, documents sources, circuit A → B → C, arbitrage (M01, M02)."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from recallpharma.api.auth import IdentityDep
from recallpharma.api.problems import Problem
from recallpharma.config import get_settings
from recallpharma.curation import service
from recallpharma.db import models as m
from recallpharma.db.audit import record
from recallpharma.db.session import get_session
from recallpharma.domain import curation as c

router = APIRouter(prefix="/v1/curation", tags=["validation"])


def get_db(session: Annotated[Session, Depends(get_session)]) -> Any:
    """Une transaction par requête : tout ou rien, publication comprise."""
    with session.begin():
        yield session


DB = Annotated[Session, Depends(get_db)]


def current_actor(db: DB, identity: IdentityDep) -> c.Actor:
    """Le compte vient du jeton Keycloak vérifié (ou de l'en-tête en mode dev) ; les contrôles de rôle restent ceux
    du domaine."""
    if identity.account_id is not None:
        return service.actor_for(db, identity.account_id)
    assert identity.login is not None
    return service.actor_for_login(db, identity.login, identity.roles)


ActorDep = Annotated[c.Actor, Depends(current_actor)]

me_router = APIRouter(tags=["compte"])


class MeOut(BaseModel):
    id: str
    display_name: str
    roles: list[str]
    can_curate: bool
    mfa_enabled: bool = False


@me_router.get("/v1/me", response_model=MeOut)
def me(db: DB, actor: ActorDep) -> MeOut:
    account = db.get(m.Account, actor.id)
    assert account is not None
    return MeOut(
        id=actor.id,
        display_name=account.display_name,
        roles=sorted(actor.roles),
        can_curate=actor.has(*c.CURATOR_ROLES) and not actor.has(c.Role.TECH_ADMIN),
        mfa_enabled=bool((mfa := db.get(m.AccountMfa, actor.id)) and mfa.enabled_at),
    )


def today() -> date:
    return get_settings().reference_date or date.today()


# --- Contrat ------------------------------------------------------------------------------------


class ComponentIn(BaseModel):
    substance_id: str
    strength_as_stated: str
    strength_value: str | None = None
    strength_unit: str | None = None
    strength_basis: str | None = None


class ProductIn(BaseModel):
    id: str | None = None
    name: str
    designation: str
    pharmaceutical_form: str
    product_type: str = "pharmaceutique"
    routes: list[str] = []
    target_species: list[str] = []
    components: list[ComponentIn]


class EventIn(BaseModel):
    type: Literal[
        "octroi",
        "renouvellement",
        "modification",
        "extension",
        "restriction",
        "transfert de titulaire",
        "suspension",
        "levée de suspension",
        "retrait d'office",
        "retrait à la demande du titulaire",
        "interdiction",
    ]
    decision_date: date
    effective_date: date
    end_date: date | None = None
    reason: str | None = None
    new_expiry_date: date | None = None


class WithdrawalIn(BaseModel):
    species: str
    commodity: str
    route: str | None = None
    dose_condition: str | None = None
    kind: Literal["valeur", "interdit", "non renseigné", "conditionnel", "sans objet"]
    value: str | None = None
    unit: Literal["heure", "jour", "degré-jour", "traite"] | None = None
    spc_text: str | None = None


class SpcIn(BaseModel):
    languages: list[str] = []
    posology: str | None = None
    contraindications: list[str] = []
    restrictions: list[dict[str, str | None]] = []
    withdrawal_periods: list[WithdrawalIn] = []


class PayloadIn(BaseModel):
    jurisdiction: str
    ma_number: str
    procedure: Literal["nationale", "communautaire"] = "nationale"
    holder: str
    manufacturer: str | None = None
    dispensing_condition: str | None = None
    grant_date: date
    expiry_date: date | None = None
    renewal_pending: bool = False
    events: list[EventIn] = []
    product: ProductIn
    spc: SpcIn | None = None


class SourceRef(BaseModel):
    document_id: int
    page: int = Field(ge=1)
    zone: str | None = None


class ProposalIn(BaseModel):
    payload: PayloadIn
    provenance: dict[str, SourceRef] = {}
    authorisation_id: str | None = None


class ProposalEdit(ProposalIn):
    expected_revision: int


class FirstValidationIn(BaseModel):
    approve: bool
    confirmed_fields: list[str] = []
    reason: str | None = None


class BlindEntryIn(BaseModel):
    ma_number: str
    components: list[dict[str, str]]  # substance_id, strength_as_stated
    posology: str | None = None
    withdrawal_periods: list[WithdrawalIn] = []


class ArbitrationIn(BaseModel):
    decision: c.ArbitrationDecision
    reason: str = Field(min_length=3)


class IssueOut(BaseModel):
    field: str
    code: str
    message: str


class ProposalOut(BaseModel):
    id: int
    state: str
    revision: int
    origin: str
    authorisation_id: str | None
    prepared_by: str
    first_validator: str | None
    second_validator: str | None
    arbiter: str | None
    arbitration_decision: str | None
    arbitration_reason: str | None
    payload: dict[str, Any] | None  # masqué pour le second validateur pendant la ressaisie
    provenance: dict[str, Any]
    discrepancies: list[dict[str, Any]] | None
    issues: list[IssueOut]
    critical_fields: dict[str, str]
    updated_at: datetime


class DocumentOut(BaseModel):
    id: int
    title: str
    nature: str
    document_date: date
    latest_edition: bool
    sha256: str | None
    filename: str | None
    replaces_document_id: int | None


def _out(p: m.Proposal, actor: c.Actor) -> ProposalOut:
    blind_phase = p.state == c.ProposalState.SECOND_REVIEW.value and actor.id not in (p.prepared_by, p.first_validator)
    return ProposalOut(
        id=p.id,
        state=p.state,
        revision=p.revision,
        origin=p.origin,
        authorisation_id=p.authorisation_id,
        prepared_by=p.prepared_by,
        first_validator=p.first_validator,
        second_validator=p.second_validator,
        arbiter=p.arbiter,
        arbitration_decision=p.arbitration_decision,
        arbitration_reason=p.arbitration_reason,
        payload=c.mask_blind_fields(p.payload) if blind_phase else p.payload,
        provenance=p.provenance,
        discrepancies=p.discrepancies,
        issues=[
            IssueOut(field=i.field, code=i.code, message=i.message)
            for i in c.publication_issues(p.payload, p.provenance)
        ],
        critical_fields={f.key: f.label for f in c.CRITICAL_FIELDS},
        updated_at=p.updated_at,
    )


def _dump(body: ProposalIn) -> tuple[dict[str, Any], dict[str, Any]]:
    return (
        body.payload.model_dump(mode="json"),
        {k: v.model_dump(mode="json") for k, v in body.provenance.items()},
    )


# --- Points d'accès -----------------------------------------------------------------------------


@router.post("/documents", status_code=201, response_model=DocumentOut)
async def upload_document(
    db: DB,
    actor: ActorDep,
    file: Annotated[UploadFile, File()],
    title: Annotated[str, Form()],
    nature: Annotated[Literal["officielle", "déclarative"], Form()],
    document_date: Annotated[date, Form()],
    latest_edition: Annotated[bool, Form()] = True,
    replaces_document_id: Annotated[int | None, Form()] = None,
) -> DocumentOut:
    """Capture immuable : empreinte SHA-256, doublon refusé, nouvelle version rattachée (CT-ING-01, CT-ING-02)."""
    c.check_prepare(actor)
    content = await file.read()
    digest = hashlib.sha256(content).hexdigest()
    if db.scalar(select(m.SourceDocument.id).where(m.SourceDocument.sha256 == digest)) is not None:
        raise Problem(409, "duplicate_document", "Ce document a déjà été déposé (même empreinte)")
    if replaces_document_id is not None and db.get(m.SourceDocument, replaces_document_id) is None:
        raise Problem(404, "not_found", "Document remplacé introuvable")
    storage = Path(get_settings().storage_dir)
    storage.mkdir(parents=True, exist_ok=True)
    target = storage / digest
    target.write_bytes(content)
    target.chmod(0o444)  # stockage objet verrouillé en production (S3 object lock)
    doc = m.SourceDocument(
        nature=nature,
        title=title,
        document_date=document_date,
        latest_edition=latest_edition,
        sha256=digest,
        storage_key=digest,
        filename=file.filename,
        media_type=file.content_type,
        size_bytes=len(content),
        replaces_document_id=replaces_document_id,
        uploaded_by=actor.id,
        uploaded_at=datetime.now(UTC),
    )
    db.add(doc)
    db.flush()
    record(
        db,
        actor=actor.id,
        action="document:dépôt",
        object_type="source_document",
        object_id=str(doc.id),
        after={"sha256": digest, "title": title, "replaces": replaces_document_id},
    )
    return DocumentOut(
        id=doc.id,
        title=doc.title,
        nature=doc.nature,
        document_date=doc.document_date,
        latest_edition=doc.latest_edition,
        sha256=digest,
        filename=doc.filename,
        replaces_document_id=replaces_document_id,
    )


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(db: DB, actor: ActorDep) -> list[DocumentOut]:
    rows = db.scalars(select(m.SourceDocument).order_by(m.SourceDocument.id.desc()))
    return [
        DocumentOut(
            id=d.id,
            title=d.title,
            nature=d.nature,
            document_date=d.document_date,
            latest_edition=d.latest_edition,
            sha256=d.sha256,
            filename=d.filename,
            replaces_document_id=d.replaces_document_id,
        )
        for d in rows
    ]


@router.get("/proposals", response_model=list[ProposalOut])
def list_proposals(db: DB, actor: ActorDep, state: str | None = None) -> list[ProposalOut]:
    stmt = select(m.Proposal).order_by(m.Proposal.updated_at.desc())
    if state:
        stmt = stmt.where(m.Proposal.state == state)
    return [_out(p, actor) for p in db.scalars(stmt)]


@router.post("/proposals", response_model=ProposalOut, status_code=201)
def create_proposal(db: DB, actor: ActorDep, body: ProposalIn) -> ProposalOut:
    payload, provenance = _dump(body)
    return _out(service.create(db, actor, payload, provenance, body.authorisation_id), actor)


@router.post("/authorisations/{authorisation_id}/proposals", response_model=ProposalOut, status_code=201)
def start_update(db: DB, actor: ActorDep, authorisation_id: str) -> ProposalOut:
    return _out(service.start_update(db, actor, authorisation_id), actor)


@router.get("/proposals/{proposal_id}", response_model=ProposalOut)
def get_proposal(db: DB, actor: ActorDep, proposal_id: int) -> ProposalOut:
    p = db.get(m.Proposal, proposal_id)
    if p is None:
        raise Problem(404, "not_found", "Proposition inconnue")
    return _out(p, actor)


@router.get("/proposals/{proposal_id}/history")
def proposal_history(db: DB, actor: ActorDep, proposal_id: int) -> list[dict[str, Any]]:
    steps = db.scalars(
        select(m.ProposalStep).where(m.ProposalStep.proposal_id == proposal_id).order_by(m.ProposalStep.id)
    )
    return [
        {
            "actor": s.actor,
            "action": s.action,
            "from": s.from_state,
            "to": s.to_state,
            "detail": s.detail,
            "at": s.created_at,
        }
        for s in steps
    ]


@router.put("/proposals/{proposal_id}", response_model=ProposalOut)
def edit_proposal(db: DB, actor: ActorDep, proposal_id: int, body: ProposalEdit) -> ProposalOut:
    payload, provenance = _dump(body)
    return _out(service.edit(db, actor, proposal_id, payload, provenance, body.expected_revision), actor)


@router.post("/proposals/{proposal_id}/submit", response_model=ProposalOut)
def submit(db: DB, actor: ActorDep, proposal_id: int) -> ProposalOut:
    return _out(service.submit(db, actor, proposal_id), actor)


@router.post("/proposals/{proposal_id}/fields/{field}/source-view")
def view_source(db: DB, actor: ActorDep, proposal_id: int, field: str) -> dict[str, Any]:
    return service.view_source(db, actor, proposal_id, field)


@router.post("/proposals/{proposal_id}/first-validation", response_model=ProposalOut)
def first_validation(db: DB, actor: ActorDep, proposal_id: int, body: FirstValidationIn) -> ProposalOut:
    p = service.first_validation(db, actor, proposal_id, body.approve, body.confirmed_fields, body.reason)
    return _out(p, actor)


@router.get("/proposals/{proposal_id}/blind-entry")
def blind_form(db: DB, actor: ActorDep, proposal_id: int) -> dict[str, Any]:
    """Fiche à ressaisir : n° d'AMM, teneurs, posologie et délais d'attente masqués (RG-10)."""
    return {"payload": service.blind_view(db, actor, proposal_id), "fields_to_enter": list(c.BLIND_FIELDS)}


@router.post("/proposals/{proposal_id}/blind-entry", response_model=ProposalOut)
def blind_entry(db: DB, actor: ActorDep, proposal_id: int, body: BlindEntryIn) -> ProposalOut:
    p = service.blind_entry(db, actor, proposal_id, body.model_dump(mode="json"), today())
    return _out(p, actor)


@router.post("/proposals/{proposal_id}/arbitration", response_model=ProposalOut)
def arbitration(db: DB, actor: ActorDep, proposal_id: int, body: ArbitrationIn) -> ProposalOut:
    return _out(service.arbitrate(db, actor, proposal_id, body.decision, body.reason, today()), actor)
