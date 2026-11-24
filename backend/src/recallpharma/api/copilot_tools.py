"""Outils du Copilot (D5) : liste fermée de points d'accès de lecture, servis au seul jeton délégué (ADR-08).

Chaque ligne porte l'identifiant de son enregistrement (RG-23) ; le total vient de l'API (RG-24) ; une sortie est
plafonnée à 50 lignes ; la juridiction est obligatoire dans toute recherche.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from recallpharma.api import registry, spc
from recallpharma.api import schemas as s
from recallpharma.api.auth import DelegationDep
from recallpharma.api.problems import Problem
from recallpharma.db import mapping
from recallpharma.db import models as m
from recallpharma.db.session import get_session
from recallpharma.domain.banners import NOT_AUTHORISED_HERE
from recallpharma.domain.comparison import Entry, compare
from recallpharma.domain.evaluation import applies_in
from recallpharma.domain.model import Status
from recallpharma.domain.selection import Candidate, Filters, WithdrawalCriterion, refine
from recallpharma.domain.withdrawal import WithdrawalUnit

router = APIRouter(prefix="/v1/copilot/tools", tags=["copilot-outils"])
DB = Annotated[Session, Depends(get_session)]

MAX_ROWS = 50
RULES_VERSION = "A2-v3"


class CopilotRow(BaseModel):
    id: str
    ma_number: str
    name: str
    designation: str
    form: str
    routes: list[str]
    species: list[str]
    substances: list[str]
    strengths: list[str]
    holder: str
    jurisdiction: str
    applies_to_requested: bool
    status: str
    expiry_date: date | None
    banners: list[s.BannerOut]
    evidence_level: str
    evidence_label: str
    verified_at: date | None
    source_title: str | None
    source_date: date | None
    withdrawal: list[s.WithdrawalOut]


class SetApartOut(BaseModel):
    id: str
    label: str


class ToolRows(BaseModel):
    result_set_id: uuid.UUID | None
    jurisdiction: str
    total: int
    rows: list[CopilotRow]
    truncated: bool
    apart: list[SetApartOut] = []
    excluded: int = 0
    elsewhere: list[CopilotRow] = []  # RG-16 : AMM d'autres juridictions, à titre d'information
    notice: str | None = None
    as_of: date
    rules_version: str = RULES_VERSION
    query: dict[str, Any]


class SearchIn(BaseModel):
    jurisdiction: str
    substance_id: str | None = None
    product_name: str | None = Field(None, max_length=100)
    species: str | None = None
    form: str | None = None
    route: str | None = None
    status: str | None = None


class WithdrawalFilterIn(BaseModel):
    species: str
    commodity: str
    max_value: Decimal = Field(ge=0)
    unit: WithdrawalUnit = WithdrawalUnit.DAY


class RefineIn(BaseModel):
    form: str | None = None
    route: str | None = None
    species: str | None = None
    status: str | None = None
    withdrawal: WithdrawalFilterIn | None = None


class Vocabulary(BaseModel):
    jurisdictions: dict[str, str]
    substances: list[str]
    species: list[str]
    statuses: list[str]
    forms: list[str]
    routes: list[str]
    rules_version: str = RULES_VERSION


class SubstanceCandidate(BaseModel):
    id: str
    inn_name: str
    score: float


def _today() -> date:
    return registry.resolve_as_of(None)


def _jurisdiction(db: Session, code: str) -> m.Jurisdiction:
    j = db.get(m.Jurisdiction, code)
    if j is None:
        raise Problem(422, "jurisdiction_not_covered", f"Juridiction non couverte : {code}")
    return j


def _row(row: m.Authorisation, day: date, requested: str) -> CopilotRow:
    a = registry._assess(row, day)
    spc = row.spc_versions[-1] if row.spc_versions else None
    p = row.product
    return CopilotRow(
        id=row.id,
        ma_number=row.ma_number,
        name=p.name,
        designation=p.designation,
        form=p.pharmaceutical_form,
        routes=p.routes,
        species=p.target_species,
        substances=[c.substance.inn_name for c in p.components],
        strengths=[f"{c.substance.inn_name} {c.strength_as_stated}" for c in p.components],
        holder=row.holder,
        jurisdiction=row.jurisdiction_code,
        applies_to_requested=applies_in(mapping.jurisdiction(row.jurisdiction), requested),
        status=a.status.value,
        expiry_date=a.expiry.date,
        banners=[s.BannerOut(rule=b.rule, level=b.level.value, text=b.text) for b in a.banners],
        evidence_level=a.evidence.level.value,
        evidence_label=a.evidence.label,
        verified_at=row.last_verified_at,
        source_title=row.source.title if row.source else None,
        source_date=row.source.document_date if row.source else None,
        withdrawal=[registry._withdrawal_out(w) for w in spc.withdrawal_periods] if spc else [],
    )


def _published(db: Session) -> list[m.Authorisation]:
    return list(
        db.scalars(
            select(m.Authorisation).where(m.Authorisation.publication_state == "publiée").order_by(m.Authorisation.id)
        )
    )


def _store(db: Session, cid: str | None, jurisdiction: str, query: dict[str, Any], ids: list[str]) -> uuid.UUID:
    rs = m.ResultSet(
        conversation_id=uuid.UUID(cid) if cid else None, jurisdiction_code=jurisdiction, query=query, record_ids=ids
    )
    db.add(rs)
    db.commit()
    return rs.id


@router.get("/vocabulary", response_model=Vocabulary)
def vocabulary(db: DB, _: DelegationDep) -> Vocabulary:
    """Listes fermées du contrôle après génération (D6) : aucun de ces termes ne peut figurer hors référence."""
    products = db.scalars(select(m.Product)).all()
    return Vocabulary(
        jurisdictions={j.code: j.name for j in db.scalars(select(m.Jurisdiction))},
        substances=sorted(x.inn_name for x in db.scalars(select(m.Substance))),
        species=sorted({sp for p in products for sp in p.target_species}),
        statuses=[st.value for st in Status],
        forms=sorted({p.pharmaceutical_form for p in products}),
        routes=sorted({r for p in products for r in p.routes}),
    )


@router.get("/substances", response_model=list[SubstanceCandidate])
def resolve_substance(
    db: DB, _: DelegationDep, q: Annotated[str, Query(min_length=2, max_length=100)]
) -> list[SubstanceCandidate]:
    unaccent = func.reg.f_unaccent
    term = unaccent(func.lower(q))
    score = func.similarity(unaccent(func.lower(m.Substance.inn_name)), term)
    rows = db.execute(
        select(m.Substance.id, m.Substance.inn_name, score.label("score"))
        .where((score > 0.3) | unaccent(func.lower(m.Substance.inn_name)).like(func.concat("%", term, "%")))
        .order_by(score.desc())
        .limit(5)
    )
    return [SubstanceCandidate(id=i, inn_name=n, score=round(float(sc), 3)) for i, n, sc in rows]


@router.post("/search", response_model=ToolRows)
def search_authorisations(db: DB, delegation: DelegationDep, body: SearchIn) -> ToolRows:
    _jurisdiction(db, body.jurisdiction)
    if not any([body.substance_id, body.product_name, body.species, body.form, body.route, body.status]):
        raise Problem(
            422, "too_broad", "Préciser au moins une substance, un produit, une espèce, une forme ou une voie"
        )
    day = _today()
    name = body.product_name.casefold() if body.product_name else None

    def wanted(row: m.Authorisation) -> bool:
        p = row.product
        return (
            (body.substance_id is None or any(c.substance_id == body.substance_id for c in p.components))
            and (name is None or name in p.name.casefold() or name in p.designation.casefold())
            and (body.species is None or body.species in p.target_species)
            and (body.form is None or body.form.casefold() in p.pharmaceutical_form.casefold())
            and (body.route is None or body.route in p.routes)
        )

    rows = [_row(r, day, body.jurisdiction) for r in _published(db) if wanted(r)]
    if body.status:
        rows = [r for r in rows if r.status == body.status]
    here = [r for r in rows if r.applies_to_requested]
    elsewhere = [r for r in rows if not r.applies_to_requested][:10]
    query = body.model_dump(mode="json")
    rs = _store(db, delegation.conversation_id, body.jurisdiction, query, [r.id for r in here])
    return ToolRows(
        result_set_id=rs,
        jurisdiction=body.jurisdiction,
        total=len(here),
        rows=here[:MAX_ROWS],
        truncated=len(here) > MAX_ROWS,
        elsewhere=elsewhere if not here else [],
        notice=NOT_AUTHORISED_HERE if not here and elsewhere else None,
        as_of=day,
        query=query,
    )


@router.post("/result-sets/{result_set_id}/refine", response_model=ToolRows)
def refine_result_set(db: DB, delegation: DelegationDep, result_set_id: uuid.UUID, body: RefineIn) -> ToolRows:
    rs = db.get(m.ResultSet, result_set_id)
    cid = uuid.UUID(delegation.conversation_id) if delegation.conversation_id else None
    if rs is None or rs.conversation_id != cid or rs.expires_at < datetime.now(UTC):
        raise Problem(404, "result_set_not_found", "Jeu de résultats inconnu ou expiré")
    day = _today()
    by_id = {r.id: r for r in db.scalars(select(m.Authorisation).where(m.Authorisation.id.in_(rs.record_ids)))}
    rows = {i: _row(by_id[i], day, rs.jurisdiction_code) for i in rs.record_ids if i in by_id}
    candidates = [
        Candidate(
            record_id=r.id,
            form=r.form,
            routes=frozenset(r.routes),
            species=frozenset(r.species),
            status=r.status,
            withdrawal=tuple(mapping.withdrawal(w) for w in _periods(by_id[r.id])),
        )
        for r in rows.values()
    ]
    w = body.withdrawal
    selection = refine(
        candidates,
        Filters(
            form=body.form,
            route=body.route,
            species=body.species,
            status=body.status,
            withdrawal=WithdrawalCriterion(w.species, w.commodity, w.max_value, w.unit) if w else None,
        ),
    )
    query = {"refines": str(rs.id), **body.model_dump(mode="json", exclude_none=True)}
    new_id = _store(db, delegation.conversation_id, rs.jurisdiction_code, query, list(selection.kept))
    kept = [rows[i] for i in selection.kept]
    return ToolRows(
        result_set_id=new_id,
        jurisdiction=rs.jurisdiction_code,
        total=len(kept),
        rows=kept[:MAX_ROWS],
        truncated=len(kept) > MAX_ROWS,
        apart=[SetApartOut(id=a.record_id, label=a.label) for a in selection.apart],
        excluded=selection.excluded,
        as_of=day,
        query=query,
    )


def _periods(row: m.Authorisation) -> list[m.WithdrawalPeriod]:
    return list(row.spc_versions[-1].withdrawal_periods) if row.spc_versions else []


@router.get("/authorisations/{authorisation_id}", response_model=s.ProductSheet)
def get_authorisation(db: DB, _: DelegationDep, authorisation_id: str) -> s.ProductSheet:
    return registry.product_sheet(db, authorisation_id)


@router.post("/authorisations/{authorisation_id}/withdrawal-end", response_model=s.WithdrawalResponse)
def compute_withdrawal_end(
    db: DB, _: DelegationDep, authorisation_id: str, body: s.WithdrawalRequest
) -> s.WithdrawalResponse:
    return registry.withdrawal_end(db, authorisation_id, body)


@router.get("/alerts", response_model=list[s.AlertOut])
def list_alerts(db: DB, _: DelegationDep, jurisdiction: str) -> list[s.AlertOut]:
    _jurisdiction(db, jurisdiction)
    return registry.list_alerts(db, jurisdiction)


@router.get("/spc-passages", response_model=spc.PassagesOut)
def search_spc_passages(
    db: DB,
    _: DelegationDep,
    q: Annotated[str, Query(min_length=2, max_length=300)],
    jurisdiction: str,
    ma_ids: spc.Ids = None,
    limit: Annotated[int, Query(ge=1, le=spc.MAX_PASSAGES)] = 8,
) -> spc.PassagesOut:
    return spc.find_passages(db, q, jurisdiction, spc._ids(ma_ids), limit)


@router.get("/authorisations/{authorisation_id}/spc/sections/{rubric}", response_model=spc.SectionOut)
def get_spc_section(
    db: DB, _: DelegationDep, authorisation_id: str, rubric: str, language: str | None = None
) -> spc.SectionOut:
    return spc.section(db, authorisation_id, rubric, language)


class CompareIn(BaseModel):
    product_name: str | None = Field(None, max_length=100)
    substance_id: str | None = None
    jurisdictions: list[str] | None = Field(None, max_length=10)


class ProductComparisonOut(BaseModel):
    product_id: str
    name: str
    designation: str
    present: list[str]
    absent: list[str]
    differences: list[str]
    rows: list[CopilotRow]


class CompareOut(BaseModel):
    jurisdictions: list[str]
    products: list[ProductComparisonOut]
    total: int
    truncated: bool
    as_of: date
    rules_version: str = RULES_VERSION


MAX_COMPARED = 10


@router.post("/compare", response_model=CompareOut)
def compare_jurisdictions(db: DB, _: DelegationDep, body: CompareIn) -> CompareOut:
    """Un produit (ou les produits d'une substance) dans plusieurs juridictions, chaque AMM avec son propre RCP."""
    if not body.product_name and not body.substance_id:
        raise Problem(422, "too_broad", "Préciser un produit ou une substance")
    codes = body.jurisdictions or [j.code for j in db.scalars(select(m.Jurisdiction).order_by(m.Jurisdiction.code))]
    for code in codes:
        _jurisdiction(db, code)
    day = _today()
    name = body.product_name.casefold() if body.product_name else None
    rows = [
        r
        for r in _published(db)
        if (name is None or name in r.product.name.casefold() or name in r.product.designation.casefold())
        and (body.substance_id is None or any(c.substance_id == body.substance_id for c in r.product.components))
    ]
    out_rows = {r.id: _row(r, day, r.jurisdiction_code) for r in rows}
    entries = [
        Entry(
            record_id=r.id,
            product_id=r.product_id,
            jurisdiction=r.jurisdiction_code,
            status=out_rows[r.id].status,
            species=frozenset(r.product.target_species),
            withdrawal=frozenset(
                (w.species, w.commodity, w.route or "", f"{w.kind} {w.value or ''} {w.unit or ''}".strip())
                for w in _periods(r)
            )
            if r.spc_versions
            else None,
        )
        for r in rows
    ]
    compared = [c for c in compare(entries, codes) if c.present]
    products = {r.product_id: r.product for r in rows}
    return CompareOut(
        jurisdictions=codes,
        products=[
            ProductComparisonOut(
                product_id=c.product_id,
                name=products[c.product_id].name,
                designation=products[c.product_id].designation,
                present=list(c.present),
                absent=list(c.absent),
                differences=list(c.differences),
                rows=[out_rows[i] for i in c.record_ids],
            )
            for c in compared[:MAX_COMPARED]
        ],
        total=len(compared),
        truncated=len(compared) > MAX_COMPARED,
        as_of=day,
    )
