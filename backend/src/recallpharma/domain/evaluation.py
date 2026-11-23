"""Évaluation complète d'une AMM à une date : ce que la fiche, l'API, le mobile et le copilote affichent."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from recallpharma.domain.banners import Banner, record_banners, regulatory_banners, substance_banners
from recallpharma.domain.evidence import Evidence, compute_evidence, verification_mentions
from recallpharma.domain.model import Jurisdiction, MarketingAuthorisation, Status, Substance
from recallpharma.domain.status import Expiry, compute_status, effective_expiry, visible_events


@dataclass(frozen=True, slots=True)
class Assessment:
    status: Status
    expiry: Expiry
    mentions: list[str]
    evidence: Evidence
    banners: list[Banner]


def assess(
    ma: MarketingAuthorisation,
    jurisdiction: Jurisdiction,
    substances: Iterable[Substance],
    as_of: date,
    known_at: date | None = None,
) -> Assessment:
    status = compute_status(ma, jurisdiction, as_of, known_at)
    return Assessment(
        status=status,
        expiry=effective_expiry(ma, jurisdiction, visible_events(ma, as_of, known_at)),
        mentions=verification_mentions(ma, jurisdiction, as_of),
        evidence=compute_evidence(ma, jurisdiction, as_of),
        banners=[
            *regulatory_banners(ma, status, as_of, known_at),
            *substance_banners(substances, jurisdiction),
            *record_banners(ma),
        ],
    )


def applies_in(ma_jurisdiction: Jurisdiction, requested: str) -> bool:
    """RG-05 : une AMM nationale vaut pour sa seule juridiction, une AMM communautaire pour ses membres."""
    return ma_jurisdiction.code == requested or requested in ma_jurisdiction.members
