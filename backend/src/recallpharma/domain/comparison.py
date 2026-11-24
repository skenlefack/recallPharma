"""Comparaison entre juridictions (D3, CU-18) : statut, numéro, espèces et délais d'attente d'un même produit.

Chaque AMM est lue avec son propre RCP : un RCP n'est jamais transposé d'une juridiction à l'autre (RG-06). Une AMM
sans RCP dans une juridiction reste sans délai d'attente, même si le produit en a un ailleurs.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

STATUS, SPECIES, WITHDRAWAL = "statut", "espèces cibles", "délais d'attente"
WithdrawalLine = tuple[str, str, str, str]  # espèce, denrée, voie, valeur


@dataclass(frozen=True, slots=True)
class Entry:
    record_id: str
    product_id: str
    jurisdiction: str
    status: str
    species: frozenset[str]
    withdrawal: frozenset[WithdrawalLine] | None  # None : pas de RCP pour cette AMM


@dataclass(frozen=True, slots=True)
class ProductComparison:
    product_id: str
    present: tuple[str, ...]  # juridictions où le produit a une AMM, dans l'ordre demandé
    absent: tuple[str, ...]
    differences: tuple[str, ...]  # rubriques qui diffèrent d'une juridiction à l'autre
    record_ids: tuple[str, ...]


def compare(entries: Sequence[Entry], jurisdictions: Sequence[str]) -> list[ProductComparison]:
    out: list[ProductComparison] = []
    for product in dict.fromkeys(e.product_id for e in entries):
        mine = [e for e in entries if e.product_id == product and e.jurisdiction in jurisdictions]
        present = tuple(j for j in jurisdictions if any(e.jurisdiction == j for e in mine))
        by_j = {j: [e for e in mine if e.jurisdiction == j] for j in present}
        differences: list[str] = []
        if len(present) > 1:
            if len({frozenset(e.status for e in v) for v in by_j.values()}) > 1:
                differences.append(STATUS)
            if len({frozenset().union(*(e.species for e in v)) for v in by_j.values()}) > 1:
                differences.append(SPECIES)
            if len({frozenset(e.withdrawal for e in v) for v in by_j.values()}) > 1:
                differences.append(WITHDRAWAL)
        out.append(
            ProductComparison(
                product_id=product,
                present=present,
                absent=tuple(j for j in jurisdictions if j not in present),
                differences=tuple(differences),
                record_ids=tuple(e.record_id for j in present for e in by_j[j]),
            )
        )
    return out
