"""Texte des RCP (D5) : rubriques d'origine et recherche de passages, filtrée sur la juridiction et la version publiée.

Un passage est rendu tel qu'il figure dans le RCP, dans sa langue, avec son AMM, sa rubrique et sa source : il n'est
ni traduit ni résumé. Un RCP ne vaut que pour l'AMM qui le porte (RG-06).
"""

from __future__ import annotations

import re
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from recallpharma.api import registry
from recallpharma.api import schemas as s
from recallpharma.api.problems import Problem
from recallpharma.db import mapping
from recallpharma.db import models as m
from recallpharma.db.session import get_session
from recallpharma.domain.evaluation import applies_in
from recallpharma.domain.passages import RUBRICS
from recallpharma.retrieval.embeddings import Embedder
from recallpharma.retrieval.search import search_passages

router = APIRouter(prefix="/v1", tags=["rcp"])
DB = Annotated[Session, Depends(get_session)]
MAX_PASSAGES = 20


class SectionText(BaseModel):
    rubric: str
    language: str
    title: str
    text: str
    page: int | None
    source_title: str | None


class SectionOut(BaseModel):
    authorisation_id: str
    ma_number: str
    product: str
    jurisdiction: str
    spc_version: str
    rubric: str
    language: str
    title: str
    text: str
    page: int | None
    source_title: str | None
    other_languages: list[str]


class PassageOut(BaseModel):
    passage_id: int
    authorisation_id: str
    ma_number: str
    product: str
    jurisdiction: str
    spc_version: str
    rubric: str
    language: str
    title: str
    rank: int
    text: str
    page: int | None
    source_title: str | None
    evidence_level: str
    verified_at: date | None
    banners: list[s.BannerOut]  # RG-15 : une AMM suspendue reste signalée, même citée par un extrait
    score: float
    full_text_rank: int | None
    vector_rank: int | None


class PassagesOut(BaseModel):
    query: str
    jurisdiction: str
    mode: str  # « hybride » ou « plein texte » (modèle de plongements injoignable ou non configuré)
    embedding_model: str | None
    as_of: date
    passages: list[PassageOut]


def _latest(row: m.Authorisation) -> m.SpcVersion | None:
    return row.spc_versions[-1] if row.spc_versions else None


def searchable(db: Session, jurisdiction: str, ma_ids: list[str] | None) -> dict[int, m.Authorisation]:
    """Versions de RCP admises : dernière version des AMM publiées qui valent dans la juridiction (RG-05)."""
    if db.get(m.Jurisdiction, jurisdiction) is None:
        raise Problem(422, "jurisdiction_not_covered", f"Juridiction non couverte : {jurisdiction}")
    stmt = select(m.Authorisation).where(m.Authorisation.publication_state == "publiée")
    if ma_ids:
        stmt = stmt.where(m.Authorisation.id.in_(ma_ids))
    out: dict[int, m.Authorisation] = {}
    for row in db.scalars(stmt):
        spc = _latest(row)
        if spc is not None and applies_in(mapping.jurisdiction(row.jurisdiction), jurisdiction):
            out[spc.id] = row
    return out


def find_passages(
    db: Session, q: str, jurisdiction: str, ma_ids: list[str] | None, limit: int, embedder: Embedder | None = None
) -> PassagesOut:
    versions = searchable(db, jurisdiction, ma_ids)
    topic = q
    if ma_ids:  # produit déjà identifié : son nom ne départage plus les rubriques, il ferait gagner la dénomination
        for name in {row.product.name for row in versions.values()}:
            topic = re.sub(re.escape(name), " ", topic, flags=re.IGNORECASE)
        topic = topic if topic.strip(" ?.!") else q
    limit = min(limit, MAX_PASSAGES)
    hits, mode, model_id = search_passages(db, topic, versions.keys(), limit=limit, embedder=embedder)
    day = registry.resolve_as_of(None)
    found = db.scalars(select(m.SpcPassage).where(m.SpcPassage.id.in_([h.passage_id for h in hits])))
    passages = {p.id: p for p in found}
    wanted = {p.section_id for p in passages.values()}
    sections = {x.id: x for x in db.scalars(select(m.SpcSection).where(m.SpcSection.id.in_(wanted)))}
    out = []
    for h in hits:
        p = passages[h.passage_id]
        sec = sections[p.section_id]
        row = versions[sec.spc_version_id]
        a = registry._assess(row, day)
        out.append(
            PassageOut(
                passage_id=p.id,
                authorisation_id=row.id,
                ma_number=row.ma_number,
                product=row.product.name,
                jurisdiction=row.jurisdiction_code,
                spc_version=row.spc_versions[-1].version_label,
                rubric=sec.rubric,
                language=sec.language,
                title=sec.title,
                rank=p.rank,
                text=p.text,
                page=sec.page,
                source_title=sec.source_title,
                evidence_level=a.evidence.level.value,
                verified_at=row.last_verified_at,
                banners=[s.BannerOut(rule=b.rule, level=b.level.value, text=b.text) for b in a.banners],
                score=h.score,
                full_text_rank=h.full_text_rank,
                vector_rank=h.vector_rank,
            )
        )
    return PassagesOut(query=q, jurisdiction=jurisdiction, mode=mode, embedding_model=model_id, as_of=day, passages=out)


def section(db: Session, authorisation_id: str, rubric: str, language: str | None) -> SectionOut:
    row = registry._published(db, authorisation_id)
    spc = _latest(row)
    if spc is None:
        raise Problem(404, "spc_not_available", registry.NO_SPC)
    if rubric not in RUBRICS:
        raise Problem(422, "unknown_rubric", f"Rubrique inconnue : {rubric}", rubrics=list(RUBRICS))
    found = [x for x in spc.sections if x.rubric == rubric]
    if not found:
        raise Problem(404, "section_not_found", f"Rubrique {rubric} absente de ce RCP")
    # Langue demandée si le RCP l'a ; sinon la langue d'origine, sans traduction (CT-COP-02).
    chosen = next((x for x in found if x.language == language), found[0])
    return SectionOut(
        authorisation_id=row.id,
        ma_number=row.ma_number,
        product=row.product.name,
        jurisdiction=row.jurisdiction_code,
        spc_version=spc.version_label,
        rubric=chosen.rubric,
        language=chosen.language,
        title=chosen.title,
        text=chosen.text,
        page=chosen.page,
        source_title=chosen.source_title,
        other_languages=[x.language for x in found if x is not chosen],
    )


Ids = Annotated[str | None, Query(description="AMM visées, séparées par des virgules")]


def _ids(ma_ids: str | None) -> list[str] | None:
    return [i.strip() for i in ma_ids.split(",") if i.strip()] if ma_ids else None


@router.get("/spc-passages", response_model=PassagesOut)
def spc_passages(
    db: DB,
    q: Annotated[str, Query(min_length=2, max_length=300)],
    jurisdiction: str,
    ma_ids: Ids = None,
    limit: Annotated[int, Query(ge=1, le=MAX_PASSAGES)] = 10,
) -> PassagesOut:
    return find_passages(db, q, jurisdiction, _ids(ma_ids), limit)


@router.get("/authorisations/{authorisation_id}/spc/sections", response_model=list[SectionText])
def list_sections(db: DB, authorisation_id: str) -> list[SectionText]:
    """Texte complet du RCP en vigueur, rubrique par rubrique, dans chacune de ses langues (ordre du document)."""
    spc = _latest(registry._published(db, authorisation_id))
    if spc is None:
        raise Problem(404, "spc_not_available", registry.NO_SPC)
    return [
        SectionText(
            rubric=x.rubric, language=x.language, title=x.title, text=x.text, page=x.page, source_title=x.source_title
        )
        for x in spc.sections
    ]


@router.get("/authorisations/{authorisation_id}/spc/sections/{rubric}", response_model=SectionOut)
def get_section(db: DB, authorisation_id: str, rubric: str, language: str | None = None) -> SectionOut:
    return section(db, authorisation_id, rubric, language)
