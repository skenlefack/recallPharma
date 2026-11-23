"""Statut calculé d'une AMM (RG-03) et date d'expiration calculée (RG-04)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from recallpharma.domain.model import (
    TERMINAL_EVENTS,
    EventType,
    Jurisdiction,
    MarketingAuthorisation,
    RegulatoryEvent,
    Status,
)


@dataclass(frozen=True, slots=True)
class Expiry:
    date: date | None  # None : durée illimitée
    computed: bool


def add_years(d: date, years: int) -> date:
    """Anniversaire à N ans ; un 29 février tombe au 28 février d'une année non bissextile."""
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, day=28)


def visible_events(ma: MarketingAuthorisation, as_of: date, known_at: date | None = None) -> list[RegulatoryEvent]:
    """Événements en vigueur à `as_of`, tels qu'on les connaissait à `known_at` (bitemporel, ADR-08)."""
    events = [e for e in ma.events if e.effective_date <= as_of]
    if known_at is not None:
        events = [e for e in events if (e.known_at or e.decision_date) <= known_at]
    return sorted(events, key=lambda e: e.effective_date)


def effective_expiry(ma: MarketingAuthorisation, jurisdiction: Jurisdiction, events: list[RegulatoryEvent]) -> Expiry:
    """RG-04 : l'échéance lue dans la source prime ; sinon dernier octroi ou renouvellement + durée."""
    renewals = [e for e in events if e.type is EventType.RENEWAL]
    if renewals:
        last = renewals[-1]
        if last.new_expiry_date is not None:
            return Expiry(last.new_expiry_date, computed=False)
        if jurisdiction.validity_years is None:
            return Expiry(None, computed=False)
        return Expiry(add_years(last.effective_date, jurisdiction.validity_years), computed=True)
    if ma.expiry_date is not None:
        return Expiry(ma.expiry_date, computed=ma.expiry_is_computed)
    if jurisdiction.validity_years is None:
        return Expiry(None, computed=False)
    return Expiry(add_years(ma.grant_date, jurisdiction.validity_years), computed=True)


def compute_status(
    ma: MarketingAuthorisation, jurisdiction: Jurisdiction, as_of: date, known_at: date | None = None
) -> Status:
    """RG-03, ordre de priorité : retirée, suspendue, renouvellement en instance, expirée à confirmer,
    non vérifiable, valide. Modification, extension, restriction et transfert ne changent rien."""
    events = visible_events(ma, as_of, known_at)
    if any(e.type in TERMINAL_EVENTS for e in events):
        return Status.WITHDRAWN
    if is_suspended(events):
        return Status.SUSPENDED
    expiry = effective_expiry(ma, jurisdiction, events)
    # L'AMM reste valide le jour même de l'échéance (CT-REF-08).
    if expiry.date is not None and expiry.date < as_of:
        return Status.RENEWAL_PENDING if ma.renewal_pending else Status.EXPIRED_TO_CONFIRM
    if ma.source is None:
        return Status.UNVERIFIABLE
    return Status.VALID


def is_suspended(events: list[RegulatoryEvent]) -> bool:
    """Une suspension reste en vigueur tant qu'aucune levée ne la suit, même si son échéance est passée."""
    last_suspension = max((e.effective_date for e in events if e.type is EventType.SUSPENSION), default=None)
    if last_suspension is None:
        return False
    last_lift = max((e.effective_date for e in events if e.type is EventType.SUSPENSION_LIFTED), default=None)
    return last_lift is None or last_lift < last_suspension
