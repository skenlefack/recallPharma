"""Contrat de l'API v1 (OpenAPI 3.1 généré par FastAPI)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class BannerOut(BaseModel):
    rule: str
    level: str
    text: str


class EvidenceOut(BaseModel):
    level: str
    label: str
    missing_for_a: str | None


class JurisdictionOut(BaseModel):
    code: str
    name: str
    kind: str
    timezone: str
    members: list[str]


class SubstanceOut(BaseModel):
    id: str
    inn_name: str
    atcvet_code: str | None
    who_category: str | None
    woah_category: str | None


class AssessmentOut(BaseModel):
    """Ce que tout canal doit afficher avec une AMM : statut calculé, preuve, bandeaux (RG-03, RG-14, RG-15)."""

    status: str
    expiry_date: date | None
    expiry_is_computed: bool
    mentions: list[str]
    evidence: EvidenceOut
    banners: list[BannerOut]


class SearchHit(BaseModel):
    authorisation_id: str
    ma_number: str
    jurisdiction: str
    applies_to_requested: bool  # RG-05 : faux = AMM étrangère, affichée comme telle
    product_id: str
    product_name: str
    designation: str
    holder: str
    substances: list[str]
    assessment: AssessmentOut


class SearchResult(BaseModel):
    query: str
    jurisdiction: str | None
    as_of: date
    hits: list[SearchHit]
    notice: str | None = None  # RG-16 quand aucune AMM ne vaut dans la juridiction demandée


class ComponentOut(BaseModel):
    substance: str
    strength_as_stated: str
    strength_value: Decimal | None
    strength_unit: str | None
    strength_basis: str | None
    who_category: str | None
    woah_category: str | None


class EventOut(BaseModel):
    type: str
    decision_date: date
    effective_date: date
    end_date: date | None
    reason: str | None


class WithdrawalOut(BaseModel):
    species: str
    commodity: str
    route: str | None
    dose_condition: str | None
    kind: str
    value: Decimal | None
    unit: str | None


class SpcOut(BaseModel):
    version_label: str
    languages: list[str]
    posology: str | None
    contraindications: list[str]
    withdrawal_periods: list[WithdrawalOut]
    restrictions: list[dict[str, str | None]]


class SourceOut(BaseModel):
    nature: str
    title: str
    document_date: date
    latest_edition: bool


class AlertOut(BaseModel):
    id: str
    type: str
    level: str
    jurisdictions: list[str]
    authorisation_ids: list[str]
    batch_numbers: list[str]
    unlisted_product: str | None
    published_at: date
    closed_at: date | None
    text: str


class ProductSheet(BaseModel):
    """Fiche en cinq vues : identité, réglementation, RCP, preuves, alertes (M04)."""

    authorisation_id: str
    as_of: date
    known_at: date | None
    identity: dict[str, str | list[str] | None]
    components: list[ComponentOut]
    jurisdiction: JurisdictionOut
    regulation: dict[str, str | int | bool | date | None]
    events: list[EventOut]
    assessment: AssessmentOut
    spc: SpcOut | None
    spc_notice: str | None  # RG-06
    source: SourceOut | None
    alerts: list[AlertOut]


class WithdrawalRequest(BaseModel):
    species: str
    commodity: str
    route: str | None = None
    last_administration: datetime = Field(description="Avec fuseau horaire, ex. 2027-09-07T14:30:00+01:00")
    water_temperature_c: Decimal | None = Field(default=None, gt=0)


class WithdrawalResponse(BaseModel):
    outcome: str
    message: str
    earliest: datetime | None
    formula: str | None
    timezone: str
    period: WithdrawalOut


class BatchCheckRequest(BaseModel):
    authorisation_id: str
    batch_number: str = Field(min_length=1, max_length=64)


class BatchCheckResponse(BaseModel):
    answer: str
    notice: str
    alert_ids: list[str]
