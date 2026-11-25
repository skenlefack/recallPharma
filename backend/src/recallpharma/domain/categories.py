"""Catégories de médicaments pour la recherche, définies par préfixe de code ATCvet des substances."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Category:
    code: str
    label: str
    description: str
    atcvet_prefixes: tuple[str, ...]


CATEGORIES: tuple[Category, ...] = (
    Category("antibiotiques", "Antibiotiques", "Antibactériens à usage systémique", ("QJ01",)),
    Category("vermifuges", "Vermifuges", "Anthelminthiques contre les vers", ("QP52",)),
    Category("endectocides", "Endectocides", "Parasites internes et externes", ("QP54",)),
    Category("antiprotozoaires", "Antiprotozoaires", "Coccidioses et protozoaires", ("QP51",)),
    Category("anti-inflammatoires", "Anti-inflammatoires", "AINS, douleur et fièvre", ("QM01",)),
)

BY_CODE = {c.code: c for c in CATEGORIES}
