"""Tests de référence : le moteur reproduit les résultats attendus des 60 AMM du jeu A10."""

from __future__ import annotations

import pytest

from recallpharma.domain.evaluation import assess
from recallpharma.seed.a10 import load

SEED = load()
RAW = {a["id"]: a for a in SEED.raw["authorisations"]}


@pytest.mark.parametrize("ma", SEED.authorisations, ids=lambda ma: ma.id)
def test_assessment_matches_expected(ma):  # type: ignore[no-untyped-def]
    expected = RAW[ma.id]["expected"]
    result = assess(
        ma,
        SEED.jurisdictions[ma.jurisdiction],
        SEED.substances_of(ma.product_id),
        as_of=SEED.reference_date,
    )
    assert result.status.value == expected["status"]
    assert result.mentions == expected["mentions"]
    assert {
        "level": result.evidence.level.value,
        "label": result.evidence.label,
        "missing_for_a": result.evidence.missing_for_a,
    } == expected["evidence"]
    assert [{"rule": b.rule, "level": b.level.value, "text": b.text} for b in result.banners] == expected["banners"]
