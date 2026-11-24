"""Passages de RCP (D4, D5) : rubriques du modèle de RCP vétérinaire, découpage en passages, fusion des rangs.

Fonctions pures. La recherche elle-même (plein texte et vecteurs) est faite par la base ; ce module fixe les règles
qui ne dépendent pas d'elle : un passage ne déborde jamais de sa rubrique, compte 300 mots au plus, et deux classements
se fusionnent par la somme des inverses des rangs (RRF), sans normaliser des scores qui ne se comparent pas.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

MAX_WORDS = 300
RRF_K = 60  # constante usuelle de la fusion des rangs ; elle amortit l'écart entre les tout premiers rangs

# Rubriques du RCP vétérinaire (modèle QRD, règlement (UE) 2019/6), dans l'ordre du document.
RUBRICS: dict[str, tuple[str, str]] = {
    "1": ("Dénomination du médicament vétérinaire", "Name of the veterinary medicinal product"),
    "2": ("Composition qualitative et quantitative", "Qualitative and quantitative composition"),
    "3.1": ("Espèces cibles", "Target species"),
    "3.2": ("Indications d'utilisation pour chaque espèce cible", "Indications for use for each target species"),
    "3.3": ("Contre-indications", "Contraindications"),
    "3.4": ("Mises en garde particulières", "Special warnings"),
    "3.5": ("Précautions particulières d'emploi", "Special precautions for use"),
    "3.9": ("Voies d'administration et posologie", "Administration routes and dosage"),
    "3.11": (
        "Restrictions particulières d'utilisation et conditions particulières d'emploi",
        "Special restrictions for use and special conditions for use",
    ),
    "3.12": ("Temps d'attente", "Withdrawal periods"),
    "6": ("Nom du titulaire de l'autorisation de mise sur le marché", "Name of the marketing authorisation holder"),
    "7": ("Numéro(s) d'autorisation de mise sur le marché", "Marketing authorisation number(s)"),
}


def rubric_title(rubric: str, language: str) -> str:
    fr, en = RUBRICS[rubric]
    return en if language == "en" else fr


@dataclass(frozen=True, slots=True)
class Chunk:
    rank: int  # rang du passage dans sa rubrique, à partir de 1
    text: str


def split_section(text: str, max_words: int = MAX_WORDS) -> list[Chunk]:
    """Découpe une rubrique en passages de `max_words` mots au plus, aux limites de phrase quand c'est possible.

    Une phrase plus longue que la limite est coupée entre deux mots : aucun passage ne dépasse la limite."""
    sentences = [s for s in re.split(r"(?<=[.;:!?])\s+", text.strip()) if s]
    chunks: list[list[str]] = []
    current: list[str] = []
    for sentence in sentences:
        words = sentence.split()
        if current and len(current) + len(words) > max_words:
            chunks.append(current)
            current = []
        while len(words) > max_words:  # phrase trop longue : coupée entre deux mots
            chunks.append(words[:max_words])
            words = words[max_words:]
        current.extend(words)
    if current:
        chunks.append(current)
    return [Chunk(i, " ".join(words)) for i, words in enumerate(chunks, start=1)]


def fuse(rankings: Iterable[Sequence[int]], k: int = RRF_K, limit: int = 10) -> list[tuple[int, float]]:
    """Fusion des rangs (RRF) : score = somme sur les classements de 1 / (k + rang). Égalité : identifiant croissant,
    pour un ordre stable d'une exécution à l'autre."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for position, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + position)
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]


def recall_at(retrieved: Sequence[str], relevant: Iterable[str], k: int = 10) -> float:
    """Rappel à k (D6) : part des éléments pertinents trouvés dans les k premiers, plafonnée par k."""
    wanted = set(relevant)
    if not wanted:
        return 1.0
    return len(wanted & set(retrieved[:k])) / min(len(wanted), k)
