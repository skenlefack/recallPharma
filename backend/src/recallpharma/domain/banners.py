"""Bandeaux affichés sur tous les canaux (RG-03, RG-11, RG-15, RG-16, RG-19, RG-20).

L'ordre est stable : décisions réglementaires, statut, substances, état de la fiche.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from recallpharma.domain.model import (
    EventType,
    Jurisdiction,
    MarketingAuthorisation,
    Status,
    Substance,
    WhoCategory,
)
from recallpharma.domain.status import visible_events

NOT_COMMUNICATED = "non communiqué"


class BannerLevel(StrEnum):
    RED = "rouge"
    ORANGE = "orange"
    GREY = "gris"


@dataclass(frozen=True, slots=True)
class Banner:
    rule: str
    level: BannerLevel
    text: str


_DO_NOT_DISPENSE = "Ne pas délivrer. Stocks et animaux déjà traités : suivre la décision ou interroger l'autorité."
_WHO_HIGHEST_PRIORITY = (
    "Antimicrobien de priorité la plus élevée pour la médecine humaine (OMS). Recommandations de l'OMSA : "
    "pas d'usage préventif ; pas en première intention sauf justification, de préférence après analyse "
    "bactériologique ; hors AMM seulement faute d'alternative ; jamais comme promoteur de croissance."
)
_WHO_CRITICAL = "Antimicrobien d'importance critique pour la médecine humaine (OMS) : usage prudent."
_WHO_HUMAN_ONLY = "Classe réservée à la médecine humaine selon l'OMS."

NOT_AUTHORISED_HERE = (
    "Non vérifié comme autorisé dans cette juridiction. Ce produit peut relever d'une dérogation "
    "ministérielle ou d'une AMM non encore intégrée : vérifier auprès de l'autorité."
)


def regulatory_banners(
    ma: MarketingAuthorisation, status: Status, as_of: date, known_at: date | None = None
) -> list[Banner]:
    """RG-15 : suspension et retrait ; RG-03 : statuts à confirmer."""
    out: list[Banner] = []
    for e in visible_events(ma, as_of, known_at):
        reason = e.reason or NOT_COMMUNICATED
        if e.type is EventType.SUSPENSION and status is Status.SUSPENDED:
            text = (
                f"AMM suspendue dans cette juridiction depuis le {e.effective_date.isoformat()}. "
                f"Motif : {reason}. {_DO_NOT_DISPENSE}"
            )
            if e.end_date is not None and e.end_date < as_of:
                text += " Échéance de la suspension dépassée : à confirmer auprès de l'autorité."
            out.append(Banner("RG-15", BannerLevel.RED, text))
        elif e.type in (EventType.WITHDRAWAL, EventType.BAN):
            verb = "retirée" if e.type is EventType.WITHDRAWAL else "interdite"
            out.append(
                Banner(
                    "RG-15",
                    BannerLevel.RED,
                    f"AMM {verb} dans cette juridiction depuis le {e.effective_date.isoformat()}. "
                    f"Motif : {reason}. {_DO_NOT_DISPENSE}",
                )
            )
        elif e.type is EventType.WITHDRAWAL_BY_HOLDER:
            out.append(
                Banner(
                    "RG-15",
                    BannerLevel.ORANGE,
                    f"AMM abandonnée par le titulaire le {e.effective_date.isoformat()} ; "
                    "écoulement des stocks selon la décision.",
                )
            )
    if status is Status.RENEWAL_PENDING:
        out.append(
            Banner(
                "RG-03",
                BannerLevel.ORANGE,
                "Renouvellement en cours d'examen ; statut à confirmer auprès de l'autorité.",
            )
        )
    elif status is Status.EXPIRED_TO_CONFIRM:
        out.append(
            Banner(
                "RG-03",
                BannerLevel.ORANGE,
                "Date d'expiration dépassée sans renouvellement connu : vérifier auprès de l'autorité.",
            )
        )
    elif status is Status.UNVERIFIABLE:
        out.append(
            Banner(
                "RG-03",
                BannerLevel.GREY,
                "Aucune source officielle exploitable : aucune valeur n'est présentée comme certaine.",
            )
        )
    return out


def substance_banners(substances: Iterable[Substance], jurisdiction: Jurisdiction) -> list[Banner]:
    """RG-19 : substances interdites ou visées par le Codex ; RG-20 : catégorie OMS, jamais OMSA seule."""
    out: list[Banner] = []
    for s in substances:
        name = s.inn_name[:1].upper() + s.inn_name[1:]
        if s.inn_name in jurisdiction.banned_substances:
            out.append(
                Banner(
                    "RG-19",
                    BannerLevel.RED,
                    f"{name} : substance interdite chez les animaux producteurs de denrées dans cette juridiction.",
                )
            )
        elif s.codex_rmr:
            out.append(
                Banner(
                    "RG-19",
                    BannerLevel.ORANGE,
                    f"{name}. Recommandation du Codex : ne pas utiliser chez les animaux producteurs de "
                    "denrées. Ce n'est pas une interdiction nationale.",
                )
            )
        if s.who_category is WhoCategory.HIGHEST_PRIORITY:
            out.append(Banner("RG-20", BannerLevel.ORANGE, _WHO_HIGHEST_PRIORITY))
        elif s.who_category is WhoCategory.CRITICAL:
            out.append(Banner("RG-20", BannerLevel.GREY, _WHO_CRITICAL))
        elif s.who_category is WhoCategory.HUMAN_ONLY:
            out.append(Banner("RG-20", BannerLevel.RED, _WHO_HUMAN_ONLY))
    return out


def record_banners(ma: MarketingAuthorisation) -> list[Banner]:
    """RG-11 : pendant un litige, la version publiée précédente reste affichée."""
    if ma.dispute_open:
        return [
            Banner(
                "RG-11",
                BannerLevel.GREY,
                "Fiche en cours de vérification : la version publiée précédente reste affichée.",
            )
        ]
    return []
