"""Teneurs (RG-07) et quantité de substance active par présentation (RG-31)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

_PERCENT = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*%\s*(m/v|p/v|m/m|p/p|v/v)?\s*$", re.IGNORECASE)

# Base déclarée d'un pourcentage → (unité normalisée, base normalisée, facteur pour 1 %)
_PERCENT_BASES = {
    "m/v": ("mg", "par mL", Decimal(10)),  # 1 % m/v = 10 mg/mL
    "p/v": ("mg", "par mL", Decimal(10)),
    "m/m": ("mg", "par g", Decimal(10)),  # 1 % m/m = 10 mg/g
    "p/p": ("mg", "par g", Decimal(10)),
    "v/v": ("mL", "par mL", Decimal("0.01")),
}


@dataclass(frozen=True, slots=True)
class Strength:
    as_stated: str  # toujours conservée telle qu'exprimée
    value: Decimal | None
    unit: str | None
    basis: str | None

    @property
    def is_ambiguous(self) -> bool:
        """RG-07 : une teneur sans valeur normalisée bloque la publication."""
        return self.value is None or self.unit is None or self.basis is None


def normalise_percentage(as_stated: str, declared_basis: str | None = None) -> Strength:
    """« 10 % » + base m/v → 100 mg par mL ; sans base déclarée, la teneur reste ambiguë."""
    m = _PERCENT.match(as_stated)
    if not m:
        raise ValueError(f"pas un pourcentage : {as_stated!r}")
    basis = (m.group(2) or declared_basis or "").lower()
    if basis not in _PERCENT_BASES:
        return Strength(as_stated, None, None, None)
    unit, per, factor = _PERCENT_BASES[basis]
    value = Decimal(m.group(1).replace(",", ".")) * factor
    return Strength(as_stated, value.normalize(), unit, per)


@dataclass(frozen=True, slots=True)
class ActiveQuantity:
    as_labelled: Decimal
    unit: str
    as_active_entity: Decimal | None  # option : sel → base par un facteur documenté
    factor_reference: str | None


def active_quantity(
    strength: Strength,
    content: Decimal,
    content_unit: str,
    active_entity_factor: Decimal | None = None,
    factor_reference: str | None = None,
) -> ActiveQuantity:
    """RG-31 : teneur × contenance ; les deux valeurs (étiquette et entité active) sont conservées."""
    if strength.is_ambiguous:
        raise ValueError("teneur ambiguë : quantité de substance active non calculable (RG-07)")
    assert strength.value is not None and strength.basis is not None and strength.unit is not None
    expected = strength.basis.removeprefix("par ").strip()
    if expected.lower() != content_unit.lower():
        raise ValueError(f"contenance en {content_unit}, teneur exprimée {strength.basis}")
    labelled = strength.value * content
    if active_entity_factor is not None and not factor_reference:
        raise ValueError("un facteur de conversion doit citer sa référence documentée")
    return ActiveQuantity(
        as_labelled=labelled,
        unit=strength.unit,
        as_active_entity=labelled * active_entity_factor if active_entity_factor is not None else None,
        factor_reference=factor_reference,
    )
