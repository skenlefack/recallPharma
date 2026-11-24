"""Passages de RCP et comparaison : découpage, fusion des rangs, rappel, différences entre juridictions."""

from __future__ import annotations

import json

from hypothesis import given
from hypothesis import strategies as st

from recallpharma.domain.comparison import SPECIES, STATUS, WITHDRAWAL, Entry, compare
from recallpharma.domain.passages import RUBRICS, fuse, recall_at, split_section
from recallpharma.seed.a10 import DEFAULT_PATH
from recallpharma.seed.spc_texts import inn_en, spc_sections

words = st.lists(st.text(alphabet="abcdefgh", min_size=1, max_size=8), min_size=0, max_size=900)


@given(words, st.integers(min_value=5, max_value=300))
def test_split_never_exceeds_the_limit_and_loses_no_word(ws: list[str], limit: int) -> None:
    text = " ".join(w + ("." if i % 7 == 6 else "") for i, w in enumerate(ws))
    chunks = split_section(text, limit)
    assert all(len(c.text.split()) <= limit for c in chunks)
    assert " ".join(c.text for c in chunks).split() == text.split()
    assert [c.rank for c in chunks] == list(range(1, len(chunks) + 1))


def test_split_keeps_sentences_together_when_they_fit() -> None:
    chunks = split_section("Un deux trois. Quatre cinq. Six sept huit.", max_words=5)
    assert [c.text for c in chunks] == ["Un deux trois. Quatre cinq.", "Six sept huit."]


def test_rank_fusion_rewards_agreement_and_is_stable() -> None:
    fused = fuse([[1, 2, 3], [3, 1, 4]], limit=4)
    assert [i for i, _ in fused] == [1, 3, 2, 4]  # 1 et 3 dans les deux classements ; 2 et 4 dans un seul
    assert fuse([[5], [6]]) == fuse([[5], [6]]) and [i for i, _ in fuse([[6], [5]])] == [5, 6]  # égalité : id


def test_recall_at_k() -> None:
    assert recall_at(["a", "b", "c"], {"a", "z"}) == 0.5
    assert recall_at([str(i) for i in range(20)], {str(i) for i in range(15)}, k=10) == 1.0  # plafonné par k
    assert recall_at([], set()) == 1.0


def _entry(rid: str, j: str, status: str = "valide", species: str = "bovins", w: tuple[str, ...] | None = ()) -> Entry:
    return Entry(rid, "prd-1", j, status, frozenset({species}), None if w is None else frozenset({w} if w else set()))


def test_comparison_flags_each_difference_and_absence() -> None:
    same = compare([_entry("a", "PA"), _entry("b", "PB")], ["PA", "PB", "CC"])[0]
    assert same.present == ("PA", "PB") and same.absent == ("CC",) and same.differences == ()
    line = ("bovins", "lait", "IM", "valeur 7 jour")
    diff = compare([_entry("a", "PA", w=line), _entry("b", "PB", "suspendue", "ovins", w=None)], ["PA", "PB"])[0]
    assert diff.differences == (STATUS, SPECIES, WITHDRAWAL)  # RCP absent au Pays B : jamais celui du Pays A


def test_generated_spc_texts_match_the_validated_fields() -> None:
    """Le texte des rubriques reprend les champs validés : un délai écrit au RCP est celui de la base."""
    raw = json.loads(DEFAULT_PATH.read_text(encoding="utf-8"))
    products = {p["id"]: p for p in raw["products"]}
    substances = {s["id"]: s for s in raw["substances"]}
    for a in raw["authorisations"]:
        sections = spc_sections(a, products[a["product_id"]], substances)
        if not a.get("spc"):
            assert sections == []
            continue
        assert {s.language for s in sections} == set(a["spc"]["languages"])
        assert {s.rubric for s in sections} == set(RUBRICS)
        for s in sections:
            if s.rubric == "3.12":
                for w in a["spc"]["withdrawal_periods"]:
                    if w["kind"] == "valeur" and w["value"]:
                        assert f"{w['value']:g} " in s.text, (a["id"], s.text)
            if s.rubric == "7":
                assert a["ma_number"] in s.text
    assert inn_en("ivermectine") == "ivermectin" and inn_en("oxytétracycline") == "oxytetracycline"
