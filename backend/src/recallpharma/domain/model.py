"""Objets du référentiel réglementaire, tels que le moteur de règles les lit.

Ce module ne dépend d'aucun cadre : les règles se testent sans serveur ni base (D4, règles de construction).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum


class EventType(StrEnum):
    GRANT = "octroi"
    RENEWAL = "renouvellement"
    VARIATION = "modification"
    EXTENSION = "extension"
    RESTRICTION = "restriction"
    TRANSFER = "transfert de titulaire"
    SUSPENSION = "suspension"
    SUSPENSION_LIFTED = "levée de suspension"
    WITHDRAWAL = "retrait d'office"
    WITHDRAWAL_BY_HOLDER = "retrait à la demande du titulaire"
    BAN = "interdiction"


#: Événements qui mettent fin à l'AMM (état final, RG-03).
TERMINAL_EVENTS = frozenset({EventType.WITHDRAWAL, EventType.WITHDRAWAL_BY_HOLDER, EventType.BAN})


class Status(StrEnum):
    """Statut calculé d'une AMM, jamais saisi (RG-03)."""

    WITHDRAWN = "retirée"
    SUSPENDED = "suspendue"
    RENEWAL_PENDING = "renouvellement en instance"
    EXPIRED_TO_CONFIRM = "expirée, à confirmer"
    UNVERIFIABLE = "non vérifiable"
    VALID = "valide"


class SourceNature(StrEnum):
    OFFICIAL = "officielle"
    DECLARATIVE = "déclarative"


class WhoCategory(StrEnum):
    """Catégories de la liste OMS 2024 des antimicrobiens d'importance médicale (RG-20)."""

    HIGHEST_PRIORITY = "importance critique, priorité la plus élevée"
    CRITICAL = "importance critique"
    HIGH = "importance élevée"
    IMPORTANT = "importante"
    HUMAN_ONLY = "autorisée chez l'homme uniquement"


@dataclass(frozen=True, slots=True)
class Jurisdiction:
    code: str
    name: str
    kind: str  # « pays » ou « communauté »
    timezone: str
    validity_years: int | None  # None : durée illimitée, aucune expiration calculée (RG-04)
    banned_list_communicated: bool = False
    banned_substances: frozenset[str] = frozenset()
    members: tuple[str, ...] = ()
    reverification_days: int = 180  # RG-13
    expiry_days: int = 365  # RG-13 : au-delà, vérification échue et niveau D
    official_source_max_age_days: int = 365  # RG-14 : 12 mois


@dataclass(frozen=True, slots=True)
class Substance:
    id: str
    inn_name: str
    atcvet_code: str | None = None
    is_antimicrobial: bool = False
    who_category: WhoCategory | None = None
    woah_category: str | None = None
    codex_rmr: bool = False  # visée par une recommandation de gestion des risques du Codex (RG-19)


@dataclass(frozen=True, slots=True)
class Source:
    nature: SourceNature
    title: str
    document_date: date
    latest_edition: bool


@dataclass(frozen=True, slots=True)
class RegulatoryEvent:
    type: EventType
    decision_date: date
    effective_date: date
    end_date: date | None = None  # échéance prévue d'une suspension
    reason: str | None = None
    new_expiry_date: date | None = None  # renouvellement : nouvelle échéance lue dans la source
    known_at: date | None = None  # temps de connaissance ; None = connu dès la décision


@dataclass(frozen=True, slots=True)
class MarketingAuthorisation:
    """AMM d'un produit dans une juridiction, avec ce qu'il faut pour en calculer statut et preuve."""

    id: str
    jurisdiction: str
    ma_number: str
    product_id: str
    procedure: str  # « nationale » ou « communautaire »
    grant_date: date
    expiry_date: date | None
    expiry_is_computed: bool
    source: Source | None
    validations: int
    last_verified_at: date
    dispute_open: bool = False
    renewal_pending: bool = False  # demande de renouvellement confirmée par l'autorité
    events: tuple[RegulatoryEvent, ...] = field(default=())
