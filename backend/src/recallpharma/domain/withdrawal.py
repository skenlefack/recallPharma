"""Délais d'attente : cinq valeurs distinctes (RG-08) et calcul de la fin du délai (RG-21)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from decimal import Decimal
from enum import StrEnum
from zoneinfo import ZoneInfo


class WithdrawalKind(StrEnum):
    VALUE = "valeur"  # y compris zéro
    PROHIBITED = "interdit"
    NOT_STATED = "non renseigné"
    CONDITIONAL = "conditionnel"
    NOT_APPLICABLE = "sans objet"


class WithdrawalUnit(StrEnum):
    HOUR = "heure"
    DAY = "jour"
    DEGREE_DAY = "degré-jour"
    MILKING = "traite"


@dataclass(frozen=True, slots=True)
class WithdrawalPeriod:
    species: str
    commodity: str
    kind: WithdrawalKind
    value: Decimal | None = None
    unit: WithdrawalUnit | None = None
    route: str | None = None
    dose_condition: str | None = None
    spc_text: str | None = None  # texte du RCP, affiché tel quel quand aucun calcul n'est possible

    def __post_init__(self) -> None:
        has_value = self.value is not None and self.unit is not None
        if (self.kind is WithdrawalKind.VALUE) != has_value:
            raise ValueError("value et unit sont obligatoires pour un délai chiffré, et nuls sinon (D5)")
        if self.value is not None and self.value < 0:
            raise ValueError("un délai d'attente ne peut pas être négatif")


class Outcome(StrEnum):
    COMPUTED = "calculé"
    NO_WITHDRAWAL = "aucun temps d'attente"
    PROHIBITED = "usage interdit"
    NOT_STATED = "délai non renseigné"
    TEXT_ONLY = "texte du RCP, sans calcul"
    NOT_APPLICABLE = "sans objet"
    MISSING_INPUT = "donnée manquante"


@dataclass(frozen=True, slots=True)
class WithdrawalResult:
    outcome: Outcome
    message: str
    earliest: datetime | None = None
    formula: str | None = None


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")


def _label(earliest: datetime) -> str:
    return f"Première collecte ou premier abattage possible à partir du {_fmt(earliest)} (heure locale)"


def _next_day_start(dt: datetime) -> datetime:
    """« Arrondi au début du jour suivant » : minuit du jour qui suit l'instant atteint (choix prudent)."""
    return datetime.combine(dt.date() + timedelta(days=1), time.min, tzinfo=dt.tzinfo)


def compute_withdrawal_end(
    period: WithdrawalPeriod,
    last_administration: datetime,
    timezone: str,
    water_temperature_c: Decimal | None = None,
) -> WithdrawalResult:
    """RG-21. `last_administration` doit porter son fuseau ; le calcul se fait dans le fuseau légal."""
    if last_administration.tzinfo is None:
        raise ValueError("la date de dernière administration doit porter un fuseau horaire")
    local = last_administration.astimezone(ZoneInfo(timezone))

    match period.kind:
        case WithdrawalKind.PROHIBITED:
            return WithdrawalResult(Outcome.PROHIBITED, "Usage interdit pour cette denrée : aucune date calculée.")
        case WithdrawalKind.NOT_STATED:
            return WithdrawalResult(
                Outcome.NOT_STATED,
                "Délai non renseigné dans la source : ce n'est pas un délai nul. Aucune date calculée.",
            )
        case WithdrawalKind.NOT_APPLICABLE:
            return WithdrawalResult(Outcome.NOT_APPLICABLE, "Sans objet pour cette denrée.")
        case WithdrawalKind.CONDITIONAL:
            return WithdrawalResult(Outcome.TEXT_ONLY, period.spc_text or "Délai conditionnel : voir le RCP.")

    assert period.value is not None and period.unit is not None
    value, unit = period.value, period.unit
    if value == 0:
        return WithdrawalResult(Outcome.NO_WITHDRAWAL, "Aucun temps d'attente.")

    match unit:
        case WithdrawalUnit.MILKING:
            return WithdrawalResult(
                Outcome.TEXT_ONLY, period.spc_text or f"{value} traites : voir le RCP, aucun calcul de date."
            )
        case WithdrawalUnit.HOUR:
            earliest = local + timedelta(hours=float(value))
            formula = f"{_fmt(local)} + {value} h = {_fmt(earliest)}, sans arrondi"
        case WithdrawalUnit.DAY:
            reached = local + timedelta(hours=24 * float(value))
            earliest = _next_day_start(reached)
            formula = f"{_fmt(local)} + {value} × 24 h = {_fmt(reached)}, arrondi au début du jour suivant"
        case WithdrawalUnit.DEGREE_DAY:
            if water_temperature_c is None or water_temperature_c <= 0:
                return WithdrawalResult(
                    Outcome.MISSING_INPUT,
                    f"Délai de {value} degrés-jours : saisir la température moyenne de l'eau pour calculer.",
                )
            days = math.ceil(value / water_temperature_c)
            reached = local + timedelta(days=days)
            earliest = _next_day_start(reached)
            formula = (
                f"{value} degrés-jours ÷ {water_temperature_c} °C = {days} jours (arrondi à l'entier "
                f"supérieur) ; {_fmt(local)} + {days} × 24 h = {_fmt(reached)}, "
                "arrondi au début du jour suivant"
            )
    return WithdrawalResult(Outcome.COMPUTED, _label(earliest), earliest, formula)
