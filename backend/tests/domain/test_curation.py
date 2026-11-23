"""Circuit de validation (M02) : champs critiques, ressaisie à l'aveugle, rôles distincts (RG-07 à RG-12, RG-32)."""

from __future__ import annotations

import copy
from datetime import date, timedelta
from typing import Any

import pytest

from recallpharma.domain import curation as c
from recallpharma.domain.evidence import EvidenceLevel, compute_evidence, verification_mentions
from recallpharma.domain.model import Jurisdiction, MarketingAuthorisation, Source, SourceNature

A = c.Actor("a", frozenset({"Validateur"}))
B = c.Actor("b", frozenset({"Validateur"}))
C = c.Actor("c", frozenset({"Validateur"}))
LEAD = c.Actor("lead", frozenset({"Responsable réglementaire"}))
TECH = c.Actor("tech", frozenset({"Administrateur technique", "Validateur"}))


def payload() -> dict[str, Any]:
    return {
        "jurisdiction": "PA",
        "ma_number": "PA-V-2027-0100",
        "holder": "Laboratoires Alpha (fictif)",
        "dispensing_condition": "sur ordonnance vétérinaire",
        "grant_date": "2027-01-10",
        "events": [{"type": "octroi", "decision_date": "2027-01-10", "effective_date": "2027-01-10"}],
        "product": {
            "name": "Produit-100",
            "designation": "oxytétracycline 100 mg/mL, solution injectable",
            "pharmaceutical_form": "solution injectable",
            "routes": ["IM"],
            "target_species": ["bovins"],
            "components": [
                {
                    "substance_id": "sub-01",
                    "strength_as_stated": "100 mg/mL",
                    "strength_value": "100",
                    "strength_unit": "mg",
                    "strength_basis": "par mL",
                }
            ],
        },
        "spc": {
            "posology": "10 mg/kg une fois par jour pendant 3 jours",
            "contraindications": [],
            "restrictions": [],
            "withdrawal_periods": [
                {
                    "species": "bovins",
                    "commodity": "viande et abats",
                    "route": "IM",
                    "kind": "valeur",
                    "value": "28",
                    "unit": "jour",
                },
                {
                    "species": "bovins",
                    "commodity": "lait",
                    "route": "IM",
                    "kind": "interdit",
                    "value": None,
                    "unit": None,
                },
            ],
        },
    }


FULL_PROVENANCE = {f.key: {"document_id": 1, "page": 2} for f in c.CRITICAL_FIELDS}


def blind_from(p: dict[str, Any]) -> dict[str, Any]:
    return {
        "ma_number": p["ma_number"],
        "components": [
            {"substance_id": x["substance_id"], "strength_as_stated": x["strength_as_stated"]}
            for x in p["product"]["components"]
        ],
        "posology": p["spc"]["posology"],
        "withdrawal_periods": p["spc"]["withdrawal_periods"],
    }


def test_fourteen_critical_fields() -> None:
    assert len(c.CRITICAL_FIELDS) == 14
    assert set(c.BLIND_FIELDS) <= c.CRITICAL_KEYS


def test_complete_proposal_has_no_issue() -> None:
    assert c.publication_issues(payload(), FULL_PROVENANCE) == []


def test_every_value_needs_a_source_rg_12() -> None:
    prov = {k: v for k, v in FULL_PROVENANCE.items() if k != "holder"}
    issues = c.publication_issues(payload(), prov)
    assert [(i.field, i.code) for i in issues] == [("holder", "no_source")]
    no_page = {**FULL_PROVENANCE, "holder": {"document_id": 1, "page": None}}
    assert c.publication_issues(payload(), no_page)[0].code == "no_source"


def test_missing_critical_value() -> None:
    p = payload()
    p["spc"]["posology"] = "  "
    assert [(i.field, i.code) for i in c.publication_issues(p, FULL_PROVENANCE)] == [("posology", "missing")]


def test_empty_prohibitions_is_a_value_not_an_absence() -> None:
    p = payload()
    assert p["spc"]["restrictions"] == []
    assert c.publication_issues(p, FULL_PROVENANCE) == []


def test_ambiguous_percentage_blocks_publication_rg_07() -> None:
    p = payload()
    p["product"]["components"][0].update(
        strength_as_stated="10 %", strength_value=None, strength_unit=None, strength_basis=None
    )
    assert [i.code for i in c.publication_issues(p, FULL_PROVENANCE)] == ["ambiguous_strength"]


def test_blind_entry_concordant_after_normalisation_rg_10() -> None:
    p = payload()
    blind = blind_from(p)
    blind["ma_number"] = "pa v 2027 0100"
    blind["components"][0]["strength_as_stated"] = "100,0 mg/ml"
    blind["posology"] = "10 MG/KG  une fois par jour pendant 3 jours"
    blind["withdrawal_periods"] = [
        {**blind["withdrawal_periods"][1]},
        {**blind["withdrawal_periods"][0], "value": "28.0"},
    ]
    assert c.compare_blind_entry(p, blind) == []


def test_blind_entry_discordant_withdrawal_ct_val_03() -> None:
    p = payload()
    blind = copy.deepcopy(blind_from(p))
    blind["withdrawal_periods"][0]["value"] = "21"
    assert [d.field for d in c.compare_blind_entry(p, blind)] == ["withdrawal_periods"]


def test_zero_and_not_stated_never_concordant_rg_08() -> None:
    p = payload()
    p["spc"]["withdrawal_periods"] = [
        {"species": "bovins", "commodity": "lait", "kind": "valeur", "value": "0", "unit": "jour"}
    ]
    blind = blind_from(p)
    blind["withdrawal_periods"] = [
        {"species": "bovins", "commodity": "lait", "kind": "non renseigné", "value": None, "unit": None}
    ]
    assert [d.field for d in c.compare_blind_entry(p, blind)] == ["withdrawal_periods"]


def test_mask_hides_blind_fields_only() -> None:
    masked = c.mask_blind_fields(payload())
    assert (
        masked["ma_number"] is None
        and masked["spc"]["withdrawal_periods"] is None
        and masked["spc"]["posology"] is None
    )
    assert masked["product"]["components"] == [{"substance_id": "sub-01"}]
    assert masked["holder"] == "Laboratoires Alpha (fictif)"
    assert payload()["ma_number"] == "PA-V-2027-0100"  # l'original n'est pas modifié


def test_apply_blind_values_for_arbitration() -> None:
    p = payload()
    blind = copy.deepcopy(blind_from(p))
    blind["withdrawal_periods"][0]["value"] = "21"
    out = c.apply_blind_values(p, blind, ["withdrawal_periods"])
    assert out["spc"]["withdrawal_periods"][0]["value"] == "21"
    assert p["spc"]["withdrawal_periods"][0]["value"] == "28"


# --- Transitions et séparation des rôles --------------------------------------------------------

P = c.ProposalState


def snap(state: c.ProposalState, b: str | None = None, c_: str | None = None) -> c.ProposalSnapshot:
    return c.ProposalSnapshot(state, "a", b, c_)


def code_of(fn: Any, *args: Any) -> str:
    with pytest.raises(c.WorkflowError) as e:
        fn(*args)
    return e.value.code


def test_happy_path() -> None:
    assert c.check_submit(snap(P.PROPOSED), A, []) is P.FIRST_REVIEW
    keys = list(c.CRITICAL_KEYS)
    assert c.check_first_validation(snap(P.FIRST_REVIEW), B, True, keys, keys, None) is P.SECOND_REVIEW
    assert c.check_blind_entry(snap(P.SECOND_REVIEW, "b"), C, []) is P.PUBLISHED
    disc = [c.Discrepancy("ma_number", "x", "y")]
    assert c.check_blind_entry(snap(P.SECOND_REVIEW, "b"), C, disc) is P.DISPUTED


def test_incomplete_submit_refused() -> None:
    assert code_of(c.check_submit, snap(P.PROPOSED), A, [c.Issue("holder", "no_source", "x")]) == "incomplete"
    assert code_of(c.check_submit, snap(P.PROPOSED), B, []) == "not_preparer"


def test_confirmation_requires_viewed_source_ct_val_01() -> None:
    keys = list(c.CRITICAL_KEYS)
    assert (
        code_of(c.check_first_validation, snap(P.FIRST_REVIEW), B, True, keys, keys[:-1], None) == "source_not_viewed"
    )
    assert (
        code_of(c.check_first_validation, snap(P.FIRST_REVIEW), B, True, keys[:3], keys, None) == "unconfirmed_fields"
    )


def test_return_to_preparer_needs_reason() -> None:
    assert code_of(c.check_first_validation, snap(P.FIRST_REVIEW), B, False, [], [], " ") == "reason_required"
    assert c.check_first_validation(snap(P.FIRST_REVIEW), B, False, [], [], "page illisible") is P.PROPOSED


def test_separation_of_duties_rg_32_ct_val_02() -> None:
    keys = list(c.CRITICAL_KEYS)
    assert code_of(c.check_first_validation, snap(P.FIRST_REVIEW), A, True, keys, keys, None) == "same_person"
    assert code_of(c.check_blind_entry, snap(P.SECOND_REVIEW, "b"), A, []) == "same_person"
    assert code_of(c.check_blind_entry, snap(P.SECOND_REVIEW, "b"), B, []) == "same_person"
    assert (
        code_of(c.check_first_validation, snap(P.FIRST_REVIEW), TECH, True, keys, keys, None)
        == "tech_admin_cannot_validate"
    )
    assert code_of(c.check_prepare, TECH) == "tech_admin_cannot_validate"


def test_arbitration_rg_11() -> None:
    disputed = snap(P.DISPUTED, "b", "lead")
    assert code_of(c.check_arbitration, disputed, LEAD, c.ArbitrationDecision.KEEP_BLIND, "ok") == "arbiter_involved"
    other_lead = c.Actor("lead2", frozenset({"Responsable réglementaire"}))
    assert code_of(c.check_arbitration, disputed, other_lead, c.ArbitrationDecision.KEEP_BLIND, "") == "reason_required"
    assert c.check_arbitration(disputed, other_lead, c.ArbitrationDecision.KEEP_BLIND, "RCP p. 4") is P.PUBLISHED
    assert c.check_arbitration(disputed, other_lead, c.ArbitrationDecision.REJECT, "doublon") is P.ARCHIVED
    product_lead = c.Actor("pl", frozenset({"Responsable produit"}))
    assert (
        c.check_arbitration(disputed, product_lead, c.ArbitrationDecision.KEEP_PREPARED, "décision p. 1") is P.PUBLISHED
    )
    assert code_of(c.check_arbitration, disputed, C, c.ArbitrationDecision.KEEP_PREPARED, "x") == "forbidden"


def test_edit_after_signature_resets_review() -> None:
    assert c.check_edit(snap(P.SECOND_REVIEW, "b"), A) is P.PROPOSED
    assert code_of(c.check_edit, snap(P.SECOND_REVIEW, "b"), B) == "not_preparer"
    assert code_of(c.check_edit, snap(P.PUBLISHED, "b", "c"), A) == "invalid_state"


# --- CT-VAL-05 : seuils de revérification -------------------------------------------------------

PA = Jurisdiction(code="PA", name="Pays A", kind="pays", timezone="Africa/Douala", validity_years=5)


@pytest.mark.parametrize(
    ("age", "level", "mentions"),
    [
        (180, EvidenceLevel.A, []),
        (181, EvidenceLevel.B, ["à revérifier"]),
        (365, EvidenceLevel.B, ["à revérifier"]),
        (366, EvidenceLevel.D, ["vérification échue depuis le 2027-08-02"]),
    ],
)
def test_reverification_thresholds_ct_val_05(age: int, level: EvidenceLevel, mentions: list[str]) -> None:
    verified = date(2026, 8, 2)
    ma = MarketingAuthorisation(
        id="x",
        jurisdiction="PA",
        ma_number="1",
        product_id="p",
        procedure="nationale",
        grant_date=date(2025, 1, 1),
        expiry_date=date(2030, 1, 1),
        expiry_is_computed=False,
        source=Source(SourceNature.OFFICIAL, "Liste", verified + timedelta(days=age) - timedelta(days=30), True),
        validations=2,
        last_verified_at=verified,
    )
    as_of = verified + timedelta(days=age)
    assert compute_evidence(ma, PA, as_of).level is level
    assert verification_mentions(ma, PA, as_of) == mentions
