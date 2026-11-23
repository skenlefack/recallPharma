"""Affinage d'un jeu de résultats du Copilot (M5, comportement 3) : filtres et décomptes déterministes (RG-24).

Filtre sur un délai d'attente : ne sont retenus que les produits dont le délai est chiffré pour l'espèce et la denrée
demandées et dont la valeur la plus longue, toutes voies et posologies confondues, respecte le critère. Les produits au
délai non renseigné, interdit ou conditionnel sont comptés et listés à part, sous leur libellé, jamais parmi les
produits retenus.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from recallpharma.domain.withdrawal import WithdrawalKind, WithdrawalPeriod, WithdrawalUnit

_HOURS = {WithdrawalUnit.HOUR: Decimal(1), WithdrawalUnit.DAY: Decimal(24)}


@dataclass(frozen=True, slots=True)
class Candidate:
    record_id: str
    form: str
    routes: frozenset[str]
    species: frozenset[str]
    status: str
    withdrawal: tuple[WithdrawalPeriod, ...] = ()


@dataclass(frozen=True, slots=True)
class WithdrawalCriterion:
    species: str
    commodity: str
    max_value: Decimal
    unit: WithdrawalUnit = WithdrawalUnit.DAY

    def __post_init__(self) -> None:
        if self.unit not in _HOURS:
            raise ValueError("critère exprimé en jours ou en heures seulement")
        if self.max_value < 0:
            raise ValueError("critère négatif")


@dataclass(frozen=True, slots=True)
class Filters:
    form: str | None = None
    route: str | None = None
    species: str | None = None
    status: str | None = None
    withdrawal: WithdrawalCriterion | None = None


@dataclass(frozen=True, slots=True)
class SetApart:
    record_id: str
    label: str


@dataclass(frozen=True, slots=True)
class Selection:
    kept: tuple[str, ...]
    apart: tuple[SetApart, ...]
    excluded: int


def _matches(text: str, wanted: str) -> bool:
    return wanted.casefold() in text.casefold()


def withdrawal_verdict(c: Candidate, criterion: WithdrawalCriterion) -> bool | str:
    """True ou False si le délai est comparable au critère ; sinon le libellé sous lequel le produit est mis à part."""
    periods = [p for p in c.withdrawal if p.species == criterion.species and p.commodity == criterion.commodity]
    if not periods:
        return f"aucun délai pour {criterion.species}, {criterion.commodity}"
    for p in periods:
        if p.kind is not WithdrawalKind.VALUE:
            return f"délai {p.kind.value}"
        if p.unit not in _HOURS:
            return f"délai en {p.unit.value if p.unit else 'unité inconnue'}, non comparable"
    longest = max(p.value * _HOURS[p.unit] for p in periods if p.value is not None and p.unit is not None)
    return longest <= criterion.max_value * _HOURS[criterion.unit]


def refine(candidates: list[Candidate], f: Filters) -> Selection:
    kept: list[str] = []
    apart: list[SetApart] = []
    excluded = 0
    for c in candidates:
        if (
            (f.form and not _matches(c.form, f.form))
            or (f.route and f.route not in c.routes)
            or (f.species and f.species not in c.species)
            or (f.status and c.status != f.status)
        ):
            excluded += 1
            continue
        if f.withdrawal is not None:
            verdict = withdrawal_verdict(c, f.withdrawal)
            if isinstance(verdict, str):
                apart.append(SetApart(c.record_id, verdict))
                continue
            if not verdict:
                excluded += 1
                continue
        kept.append(c.record_id)
    return Selection(tuple(kept), tuple(apart), excluded)
