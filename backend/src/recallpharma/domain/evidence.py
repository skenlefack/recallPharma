"""Niveau de preuve A–D (RG-14) et mentions d'ancienneté de vérification (RG-13)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from recallpharma.domain.model import Jurisdiction, MarketingAuthorisation, SourceNature


class EvidenceLevel(StrEnum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"


LABELS = {
    EvidenceLevel.A: "Confirmé",
    EvidenceLevel.B: "À revérifier",
    EvidenceLevel.C: "Déclaratif",
    EvidenceLevel.D: "Non vérifiable",
}


@dataclass(frozen=True, slots=True)
class Evidence:
    level: EvidenceLevel
    missing_for_a: str | None  # ce qui manque pour atteindre A (CT-REG-05)

    @property
    def label(self) -> str:
        return LABELS[self.level]


def _evidence(level: EvidenceLevel, missing: str | None = None) -> Evidence:
    return Evidence(level, missing)


def compute_evidence(ma: MarketingAuthorisation, jurisdiction: Jurisdiction, as_of: date) -> Evidence:
    verified_age = (as_of - ma.last_verified_at).days
    source = ma.source
    if source is None:
        return _evidence(EvidenceLevel.D, "aucune source exploitable")
    if verified_age > jurisdiction.expiry_days:
        lapsed = ma.last_verified_at + timedelta(days=jurisdiction.expiry_days)
        return _evidence(EvidenceLevel.D, f"vérification échue depuis le {lapsed.isoformat()}")
    if source.nature is SourceNature.DECLARATIVE:
        return _evidence(EvidenceLevel.C, "confirmation par un document de l'autorité")
    if verified_age > jurisdiction.reverification_days:
        due = ma.last_verified_at + timedelta(days=jurisdiction.reverification_days)
        return _evidence(EvidenceLevel.B, f"revérification due depuis le {due.isoformat()}")
    if ma.dispute_open:
        return _evidence(EvidenceLevel.B, "litige ouvert : en cours de vérification")
    source_age = (as_of - source.document_date).days
    if source_age > jurisdiction.official_source_max_age_days or not source.latest_edition:
        return _evidence(EvidenceLevel.B, "source officielle ancienne : édition de moins de 12 mois attendue")
    if ma.validations < 2:
        return _evidence(EvidenceLevel.B, "seconde validation")
    return _evidence(EvidenceLevel.A)


def verification_mentions(ma: MarketingAuthorisation, jurisdiction: Jurisdiction, as_of: date) -> list[str]:
    """RG-13 : mentions ajoutées au statut, sans le remplacer."""
    age = (as_of - ma.last_verified_at).days
    if age > jurisdiction.expiry_days:
        lapsed = ma.last_verified_at + timedelta(days=jurisdiction.expiry_days)
        return [f"vérification échue depuis le {lapsed.isoformat()}"]
    if age > jurisdiction.reverification_days:
        return ["à revérifier"]
    return []
