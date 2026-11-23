"""Vérification d'un numéro de lot contre les rappels publiés (RG-22)."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

NOT_AUTHENTICATION = "Ne constitue pas une authentification."
RECALLED = "lot visé par un rappel publié"
NO_KNOWN_RECALL = "aucun rappel publié connu"


@dataclass(frozen=True, slots=True)
class BatchRecall:
    alert_id: str
    ma_id: str
    batch_numbers: frozenset[str]
    published_at: date
    closed_at: date | None = None


@dataclass(frozen=True, slots=True)
class BatchCheck:
    answer: str
    notice: str
    alert_ids: tuple[str, ...]


def normalise_batch(number: str) -> str:
    return "".join(number.split()).upper()


def check_batch(ma_id: str, batch_number: str, recalls: Iterable[BatchRecall], as_of: date) -> BatchCheck:
    """Deux réponses possibles, jamais « authentique ». Un rappel clos continue de viser ses lots."""
    wanted = normalise_batch(batch_number)
    hits = tuple(
        r.alert_id
        for r in recalls
        if r.ma_id == ma_id and r.published_at <= as_of and wanted in {normalise_batch(b) for b in r.batch_numbers}
    )
    return BatchCheck(RECALLED if hits else NO_KNOWN_RECALL, NOT_AUTHENTICATION, hits)
