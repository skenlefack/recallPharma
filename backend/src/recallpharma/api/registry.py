"""Points d'accès de lecture du registre (M04, M06). Seules les fiches publiées sont visibles."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from recallpharma.api import schemas as s
from recallpharma.api.problems import Problem
from recallpharma.config import get_settings
from recallpharma.db import mapping
from recallpharma.db import models as m
from recallpharma.db.session import get_session
from recallpharma.domain.banners import NOT_AUTHORISED_HERE
from recallpharma.domain.batch import BatchRecall, check_batch
from recallpharma.domain.categories import BY_CODE, CATEGORIES, Category
from recallpharma.domain.evaluation import Assessment, applies_in, assess
from recallpharma.domain.identifiers import normalise_ma_number
from recallpharma.domain.withdrawal import compute_withdrawal_end

router = APIRouter(prefix="/v1", tags=["registre"])
DB = Annotated[Session, Depends(get_session)]

OFF_LABEL = (
    "Hors AMM dans cette juridiction : usage sous la seule responsabilité d'un vétérinaire, "
    "dans les conditions de la réglementation. Aucune date de fin n'est calculée."
)
NO_SPC = "RCP non disponible pour cette juridiction."


def resolve_as_of(as_of: date | None) -> date:
    return as_of or get_settings().reference_date or date.today()


AsOf = Annotated[date | None, Query(description="Date d'effet (défaut : aujourd'hui)")]
KnownAt = Annotated[date | None, Query(description="Temps de connaissance : « ce que nous savions à cette date »")]


def _assessment_out(a: Assessment) -> s.AssessmentOut:
    return s.AssessmentOut(
        status=a.status.value,
        expiry_date=a.expiry.date,
        expiry_is_computed=a.expiry.computed,
        mentions=a.mentions,
        evidence=s.EvidenceOut(
            level=a.evidence.level.value, label=a.evidence.label, missing_for_a=a.evidence.missing_for_a
        ),
        banners=[s.BannerOut(rule=b.rule, level=b.level.value, text=b.text) for b in a.banners],
    )


def _assess(row: m.Authorisation, as_of: date, known_at: date | None = None) -> Assessment:
    return assess(
        mapping.authorisation(row),
        mapping.jurisdiction(row.jurisdiction),
        [mapping.substance(c.substance) for c in row.product.components],
        as_of=as_of,
        known_at=known_at,
    )


def _published(db: Session, authorisation_id: str) -> m.Authorisation:
    row = db.get(m.Authorisation, authorisation_id)
    if row is None or row.publication_state != "publiée":
        raise Problem(404, "not_found", "AMM inconnue ou non publiée")
    return row


@router.get("/jurisdictions", response_model=list[s.JurisdictionOut])
def list_jurisdictions(db: DB) -> list[s.JurisdictionOut]:
    rows = db.scalars(select(m.Jurisdiction).order_by(m.Jurisdiction.code))
    return [
        s.JurisdictionOut(code=j.code, name=j.name, kind=j.kind, timezone=j.timezone, members=j.members) for j in rows
    ]


@router.get("/substances", response_model=list[s.SubstanceOut])
def list_substances(db: DB) -> list[s.SubstanceOut]:
    rows = db.scalars(select(m.Substance).order_by(m.Substance.inn_name))
    return [
        s.SubstanceOut(
            id=x.id,
            inn_name=x.inn_name,
            atcvet_code=x.atcvet_code,
            who_category=x.who_category,
            woah_category=x.woah_category,
        )
        for x in rows
    ]


def _in_category(category: Category) -> Select[str]:
    """AMM dont au moins une substance a un code ATCvet de la catégorie."""
    return (
        select(m.ProductComponent.product_id)
        .join(m.Substance, m.Substance.id == m.ProductComponent.substance_id)
        .where(or_(*(m.Substance.atcvet_code.startswith(p) for p in category.atcvet_prefixes)))
    )


@router.get("/categories", response_model=list[s.CategoryOut])
def list_categories(db: DB) -> list[s.CategoryOut]:
    out = []
    for c in CATEGORIES:
        count = db.scalar(
            select(func.count(m.Authorisation.id))
            .where(m.Authorisation.publication_state == "publiée")
            .where(m.Authorisation.product_id.in_(_in_category(c)))
        )
        out.append(s.CategoryOut(code=c.code, label=c.label, description=c.description, count=count or 0))
    return out


@router.get("/search", response_model=s.SearchResult)
def search(
    db: DB,
    q: Annotated[
        str | None, Query(min_length=2, max_length=100, description="Nom, substance, n° d'AMM ou titulaire")
    ] = None,
    category: Annotated[str | None, Query(description="Catégorie de médicament (voir /v1/categories)")] = None,
    jurisdiction: str | None = None,
    as_of: AsOf = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> s.SearchResult:
    if q is None and category is None:
        raise Problem(422, "validation", "Indiquer un texte à rechercher ou une catégorie")
    if category is not None and category not in BY_CODE:
        raise Problem(422, "validation", "Catégorie inconnue")
    day = resolve_as_of(as_of)
    unaccent = func.reg.f_unaccent
    stmt = (
        select(m.Authorisation.id)
        .join(m.Product, m.Authorisation.product_id == m.Product.id)
        .join(m.ProductComponent, m.ProductComponent.product_id == m.Product.id)
        .join(m.Substance, m.Substance.id == m.ProductComponent.substance_id)
        .where(m.Authorisation.publication_state == "publiée")
        .group_by(m.Authorisation.id, m.Product.id)
        .limit(limit * 3)
    )
    if category is not None:
        stmt = stmt.where(m.Authorisation.product_id.in_(_in_category(BY_CODE[category])))
    if q is None:
        stmt = stmt.order_by(m.Product.name, m.Authorisation.id)
    else:
        term = unaccent(func.lower(q))
        pattern = func.concat("%", term, "%")
        number = f"%{normalise_ma_number(q)}%"
        score = func.greatest(
            func.similarity(unaccent(func.lower(m.Product.designation)), term),
            func.similarity(unaccent(func.lower(m.Product.name)), term),
            func.coalesce(func.max(func.similarity(unaccent(func.lower(m.Substance.inn_name)), term)), 0),
        )
        stmt = stmt.where(
            or_(
                unaccent(func.lower(m.Product.designation)).like(pattern),
                unaccent(func.lower(m.Product.name)).like(pattern),
                unaccent(func.lower(m.Substance.inn_name)).like(pattern),
                unaccent(func.lower(m.Authorisation.holder)).like(pattern),
                m.Authorisation.ma_number_normalized.like(number),
                func.similarity(unaccent(func.lower(m.Substance.inn_name)), term) > 0.4,  # fautes de frappe
                func.similarity(unaccent(func.lower(m.Product.name)), term) > 0.4,
            )
        ).order_by(score.desc(), m.Authorisation.id)
    ranked = list(db.scalars(stmt))
    rows = {r.id: r for r in db.scalars(select(m.Authorisation).where(m.Authorisation.id.in_(ranked)))}
    hits: list[s.SearchHit] = []
    for row in (rows[i] for i in ranked):
        juris = mapping.jurisdiction(row.jurisdiction)
        applies = jurisdiction is None or applies_in(juris, jurisdiction)
        hits.append(
            s.SearchHit(
                authorisation_id=row.id,
                ma_number=row.ma_number,
                jurisdiction=row.jurisdiction_code,
                applies_to_requested=applies,
                product_id=row.product.id,
                product_name=row.product.name,
                designation=row.product.designation,
                holder=row.holder,
                substances=[c.substance.inn_name for c in row.product.components],
                assessment=_assessment_out(_assess(row, day)),
            )
        )
    hits.sort(key=lambda h: not h.applies_to_requested)  # tri stable : pertinence conservée
    hits = hits[:limit]
    notice = None
    if jurisdiction is not None and not any(h.applies_to_requested for h in hits):
        notice = NOT_AUTHORISED_HERE  # RG-16 : jamais « interdit »
    return s.SearchResult(
        query=q or "", category=category, jurisdiction=jurisdiction, as_of=day, hits=hits, notice=notice
    )


def _alert_out(a: m.SafetyNotice) -> s.AlertOut:
    return s.AlertOut(
        id=a.id,
        type=a.type,
        level=a.level,
        jurisdictions=a.jurisdictions,
        authorisation_ids=a.authorisation_ids,
        batch_numbers=a.batch_numbers,
        unlisted_product=a.unlisted_product,
        published_at=a.published_at,
        closed_at=a.closed_at,
        text=a.text,
    )


@router.get("/authorisations/{authorisation_id}", response_model=s.ProductSheet)
def product_sheet(db: DB, authorisation_id: str, as_of: AsOf = None, known_at: KnownAt = None) -> s.ProductSheet:
    row = _published(db, authorisation_id)
    day = resolve_as_of(as_of)
    p, j = row.product, row.jurisdiction
    spc = row.spc_versions[-1] if row.spc_versions else None
    alerts = db.scalars(
        select(m.SafetyNotice)
        .where(m.SafetyNotice.authorisation_ids.contains([row.id]), m.SafetyNotice.published_at <= day)
        .order_by(m.SafetyNotice.published_at.desc())
    )
    return s.ProductSheet(
        authorisation_id=row.id,
        as_of=day,
        known_at=known_at,
        identity={
            "product_id": p.id,
            "name": p.name,
            "designation": p.designation,
            "pharmaceutical_form": p.pharmaceutical_form,
            "product_type": p.product_type,
            "routes": p.routes,
            "target_species": p.target_species,
        },
        components=[
            s.ComponentOut(
                substance=c.substance.inn_name,
                strength_as_stated=c.strength_as_stated,
                strength_value=c.strength_value,
                strength_unit=c.strength_unit,
                strength_basis=c.strength_basis,
                who_category=c.substance.who_category,
                woah_category=c.substance.woah_category,
            )
            for c in p.components
        ],
        jurisdiction=s.JurisdictionOut(code=j.code, name=j.name, kind=j.kind, timezone=j.timezone, members=j.members),
        regulation={
            "ma_number": row.ma_number,
            "procedure": row.procedure,
            "holder": row.holder,
            "manufacturer": row.manufacturer,
            "dispensing_condition": row.dispensing_condition,
            "grant_date": row.grant_date,
            "validations": row.validations,
            "last_verified_at": row.last_verified_at,
        },
        events=[
            s.EventOut(
                type=e.type,
                decision_date=e.decision_date,
                effective_date=e.effective_date,
                end_date=e.end_date,
                reason=e.reason,
            )
            for e in row.events
            if e.effective_date <= day and (known_at is None or e.recorded_at.date() <= known_at)
        ],
        assessment=_assessment_out(_assess(row, day, known_at)),
        spc=s.SpcOut(
            version_label=spc.version_label,
            languages=spc.languages,
            posology=spc.posology,
            contraindications=spc.contraindications,
            withdrawal_periods=[_withdrawal_out(w) for w in spc.withdrawal_periods],
            restrictions=spc.restrictions,
        )
        if spc
        else None,
        spc_notice=None if spc else NO_SPC,
        source=s.SourceOut(
            nature=row.source.nature,
            title=row.source.title,
            document_date=row.source.document_date,
            latest_edition=row.source.latest_edition,
        )
        if row.source
        else None,
        alerts=[_alert_out(a) for a in alerts],
    )


def _withdrawal_out(w: m.WithdrawalPeriod) -> s.WithdrawalOut:
    return s.WithdrawalOut(
        species=w.species,
        commodity=w.commodity,
        route=w.route,
        dose_condition=w.dose_condition,
        kind=w.kind,
        value=w.value,
        unit=w.unit,
    )


@router.post("/authorisations/{authorisation_id}/withdrawal-end", response_model=s.WithdrawalResponse)
def withdrawal_end(db: DB, authorisation_id: str, body: s.WithdrawalRequest) -> s.WithdrawalResponse:
    """RG-21. Plusieurs délais possibles sans voie pour les départager : erreur, aucun délai retenu par défaut."""
    row = _published(db, authorisation_id)
    if body.last_administration.tzinfo is None:
        raise Problem(422, "naive_datetime", "La date de dernière administration doit porter son fuseau horaire")
    spc = row.spc_versions[-1] if row.spc_versions else None
    if spc is None:
        raise Problem(404, "no_spc", NO_SPC)
    candidates = [
        w
        for w in spc.withdrawal_periods
        if w.species == body.species
        and w.commodity == body.commodity
        and (body.route is None or w.route is None or w.route == body.route)
    ]
    if not candidates:
        raise Problem(422, "off_label", OFF_LABEL)  # RG-18
    if len(candidates) > 1:
        raise Problem(
            409,
            "ambiguous_withdrawal_period",
            "Plusieurs délais correspondent : préciser la voie ou la posologie",
            candidates=[_withdrawal_out(w).model_dump(mode="json") for w in candidates],
        )
    period = candidates[0]
    tz = row.jurisdiction.timezone
    result = compute_withdrawal_end(mapping.withdrawal(period), body.last_administration, tz, body.water_temperature_c)
    return s.WithdrawalResponse(
        outcome=result.outcome.value,
        message=result.message,
        earliest=result.earliest,
        formula=result.formula,
        timezone=tz,
        period=_withdrawal_out(period),
    )


@router.get("/alerts", response_model=list[s.AlertOut])
def list_alerts(db: DB, jurisdiction: str | None = None, as_of: AsOf = None) -> list[s.AlertOut]:
    day = resolve_as_of(as_of)
    stmt = select(m.SafetyNotice).where(m.SafetyNotice.published_at <= day)
    if jurisdiction:
        stmt = stmt.where(m.SafetyNotice.jurisdictions.contains([jurisdiction]))
    return [_alert_out(a) for a in db.scalars(stmt.order_by(m.SafetyNotice.published_at.desc()))]


@router.post("/batch-check", response_model=s.BatchCheckResponse)
def batch_check(db: DB, body: s.BatchCheckRequest, as_of: AsOf = None) -> s.BatchCheckResponse:
    """RG-22 : « lot visé par un rappel publié » ou « aucun rappel publié connu », jamais « authentique »."""
    _published(db, body.authorisation_id)
    rows = db.scalars(
        select(m.SafetyNotice).where(
            m.SafetyNotice.authorisation_ids.contains([body.authorisation_id]),
            func.cardinality(m.SafetyNotice.batch_numbers) > 0,
        )
    )
    recalls = [
        BatchRecall(r.id, body.authorisation_id, frozenset(r.batch_numbers), r.published_at, r.closed_at) for r in rows
    ]
    result = check_batch(body.authorisation_id, body.batch_number, recalls, resolve_as_of(as_of))
    return s.BatchCheckResponse(answer=result.answer, notice=result.notice, alert_ids=list(result.alert_ids))
