"""Cas de test des règles hors jeu A10 (A3 : CT-REF-02, CT-REF-06, CT-REF-08, CT-ALR-03 ; RG-08, RG-21)."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given
from hypothesis import strategies as st

from recallpharma.domain.batch import NO_KNOWN_RECALL, RECALLED, BatchRecall, check_batch
from recallpharma.domain.evaluation import applies_in
from recallpharma.domain.model import (
    EventType,
    Jurisdiction,
    MarketingAuthorisation,
    RegulatoryEvent,
    Source,
    SourceNature,
    Status,
)
from recallpharma.domain.status import add_years, compute_status, effective_expiry
from recallpharma.domain.strength import active_quantity, normalise_percentage
from recallpharma.domain.withdrawal import (
    Outcome,
    WithdrawalKind,
    WithdrawalPeriod,
    WithdrawalUnit,
    compute_withdrawal_end,
)

DOUALA = "Africa/Douala"
PA = Jurisdiction(code="PA", name="Pays A", kind="pays", timezone=DOUALA, validity_years=5)
CC = Jurisdiction(
    code="CC",
    name="Communauté C",
    kind="communauté",
    timezone="Africa/Dakar",
    validity_years=5,
    members=("C1", "C2"),
)
SRC = Source(SourceNature.OFFICIAL, "Liste (SPÉCIMEN)", date(2027, 6, 1), latest_edition=True)


def ma(**kw: object) -> MarketingAuthorisation:
    base = MarketingAuthorisation(
        id="amm-x",
        jurisdiction="PA",
        ma_number="PA-V-1",
        product_id="prd-x",
        procedure="nationale",
        grant_date=date(2022, 9, 7),
        expiry_date=date(2027, 9, 7),
        expiry_is_computed=False,
        source=SRC,
        validations=2,
        last_verified_at=date(2027, 8, 1),
        events=(RegulatoryEvent(EventType.GRANT, date(2022, 9, 7), date(2022, 9, 7)),),
    )
    return replace(base, **kw)  # type: ignore[arg-type]


def ev(t: EventType, d: date, **kw: object) -> RegulatoryEvent:
    return RegulatoryEvent(t, d, d, **kw)  # type: ignore[arg-type]


# --- RG-03 / RG-04 ------------------------------------------------------------------------------


def test_expiry_boundary_ct_ref_08() -> None:
    a = ma()
    assert compute_status(a, PA, date(2027, 9, 6)) is Status.VALID
    assert compute_status(a, PA, date(2027, 9, 7)) is Status.VALID
    assert compute_status(a, PA, date(2027, 9, 8)) is Status.EXPIRED_TO_CONFIRM


def test_suspension_then_lift_ct_ref_08() -> None:
    a = ma(expiry_date=date(2030, 1, 1))
    suspended = replace(a, events=(*a.events, ev(EventType.SUSPENSION, date(2027, 1, 10))))
    assert compute_status(suspended, PA, date(2027, 2, 1)) is Status.SUSPENDED
    lifted = replace(suspended, events=(*suspended.events, ev(EventType.SUSPENSION_LIFTED, date(2027, 3, 1))))
    assert compute_status(lifted, PA, date(2027, 2, 1)) is Status.SUSPENDED
    assert compute_status(lifted, PA, date(2027, 3, 1)) is Status.VALID


def test_priority_withdrawal_beats_everything() -> None:
    a = ma(source=None, expiry_date=date(2020, 1, 1), renewal_pending=True)
    a = replace(a, events=(*a.events, ev(EventType.SUSPENSION, date(2021, 1, 1)), ev(EventType.BAN, date(2021, 6, 1))))
    assert compute_status(a, PA, date(2027, 1, 1)) is Status.WITHDRAWN


@pytest.mark.parametrize("t", [EventType.VARIATION, EventType.EXTENSION, EventType.RESTRICTION, EventType.TRANSFER])
def test_neutral_events_do_not_change_status(t: EventType) -> None:
    a = ma(expiry_date=date(2030, 1, 1))
    assert compute_status(replace(a, events=(*a.events, ev(t, date(2027, 1, 1)))), PA, date(2027, 6, 1)) is Status.VALID


def test_computed_expiry_rg_04() -> None:
    a = ma(expiry_date=None)
    exp = effective_expiry(a, PA, list(a.events))
    assert exp.date == date(2027, 9, 7) and exp.computed
    renewed = [*a.events, ev(EventType.RENEWAL, date(2027, 8, 1))]
    assert effective_expiry(a, PA, renewed).date == date(2032, 8, 1)
    unlimited = replace(PA, validity_years=None)
    assert effective_expiry(a, unlimited, list(a.events)).date is None
    assert add_years(date(2024, 2, 29), 5) == date(2029, 2, 28)


def test_bitemporal_known_at() -> None:
    """« Qu'avons-nous répondu le 7 ? » : une suspension enregistrée le 10 n'était pas connue le 7."""
    susp = RegulatoryEvent(EventType.SUSPENSION, date(2027, 3, 1), date(2027, 3, 1), known_at=date(2027, 3, 10))
    a = ma(expiry_date=date(2030, 1, 1))
    a = replace(a, events=(*a.events, susp))
    assert compute_status(a, PA, as_of=date(2027, 3, 7), known_at=date(2027, 3, 7)) is Status.VALID
    assert compute_status(a, PA, as_of=date(2027, 3, 7)) is Status.SUSPENDED


def test_community_authorisation_rg_05_ct_ref_06() -> None:
    assert applies_in(CC, "C1") and applies_in(CC, "C2") and applies_in(CC, "CC")
    assert not applies_in(CC, "PA")
    assert not applies_in(PA, "C1")


# --- RG-08 / RG-21 ------------------------------------------------------------------------------

ADMIN = datetime(2027, 9, 7, 14, 30, tzinfo=ZoneInfo(DOUALA))


def wp(kind: WithdrawalKind, value: str | None = None, unit: WithdrawalUnit | None = None) -> WithdrawalPeriod:
    return WithdrawalPeriod("bovins", "lait", kind, Decimal(value) if value else None, unit)


def test_five_distinct_values_rg_08() -> None:
    outcomes = {
        compute_withdrawal_end(wp(WithdrawalKind.VALUE, "0", WithdrawalUnit.DAY), ADMIN, DOUALA).outcome,
        compute_withdrawal_end(wp(WithdrawalKind.PROHIBITED), ADMIN, DOUALA).outcome,
        compute_withdrawal_end(wp(WithdrawalKind.NOT_STATED), ADMIN, DOUALA).outcome,
        compute_withdrawal_end(wp(WithdrawalKind.CONDITIONAL), ADMIN, DOUALA).outcome,
        compute_withdrawal_end(wp(WithdrawalKind.NOT_APPLICABLE), ADMIN, DOUALA).outcome,
    }
    assert len(outcomes) == 5
    assert all(r is not Outcome.COMPUTED for r in outcomes)


def test_value_requires_unit() -> None:
    with pytest.raises(ValueError):
        WithdrawalPeriod("bovins", "lait", WithdrawalKind.VALUE, Decimal(7), None)
    with pytest.raises(ValueError):
        WithdrawalPeriod("bovins", "lait", WithdrawalKind.PROHIBITED, Decimal(7), WithdrawalUnit.DAY)


def test_hours_without_rounding() -> None:
    r = compute_withdrawal_end(wp(WithdrawalKind.VALUE, "72", WithdrawalUnit.HOUR), ADMIN, DOUALA)
    assert r.earliest == datetime(2027, 9, 10, 14, 30, tzinfo=ZoneInfo(DOUALA))
    assert r.formula and "sans arrondi" in r.formula


def test_days_rounded_to_next_day_start() -> None:
    r = compute_withdrawal_end(wp(WithdrawalKind.VALUE, "28", WithdrawalUnit.DAY), ADMIN, DOUALA)
    assert r.earliest == datetime(2027, 10, 6, 0, 0, tzinfo=ZoneInfo(DOUALA))
    assert r.message.startswith("Première collecte ou premier abattage possible à partir du 2027-10-06 00:00")


def test_evaluated_in_jurisdiction_timezone() -> None:
    utc_admin = datetime(2027, 9, 7, 23, 30, tzinfo=ZoneInfo("UTC"))  # 00:30 le 8 à Douala
    r = compute_withdrawal_end(wp(WithdrawalKind.VALUE, "1", WithdrawalUnit.DAY), utc_admin, DOUALA)
    assert r.earliest == datetime(2027, 9, 10, 0, 0, tzinfo=ZoneInfo(DOUALA))


def test_degree_days() -> None:
    period = WithdrawalPeriod("tilapia", "chair", WithdrawalKind.VALUE, Decimal(500), WithdrawalUnit.DEGREE_DAY)
    assert compute_withdrawal_end(period, ADMIN, DOUALA).outcome is Outcome.MISSING_INPUT
    r = compute_withdrawal_end(period, ADMIN, DOUALA, water_temperature_c=Decimal(27))
    # 500 / 27 = 18,5 → 19 jours ; 2027-09-26 14:30 → début du 27
    assert r.earliest == datetime(2027, 9, 27, 0, 0, tzinfo=ZoneInfo(DOUALA))


def test_naive_datetime_refused() -> None:
    with pytest.raises(ValueError):
        compute_withdrawal_end(wp(WithdrawalKind.VALUE, "1", WithdrawalUnit.DAY), datetime(2027, 1, 1), DOUALA)


@given(days=st.integers(min_value=1, max_value=400), minutes=st.integers(min_value=0, max_value=60 * 24 * 365))
def test_day_result_is_midnight_and_never_early(days: int, minutes: int) -> None:
    admin = datetime(2027, 1, 1, tzinfo=ZoneInfo(DOUALA)) + timedelta(minutes=minutes)
    r = compute_withdrawal_end(wp(WithdrawalKind.VALUE, str(days), WithdrawalUnit.DAY), admin, DOUALA)
    assert r.earliest is not None
    assert (r.earliest.hour, r.earliest.minute) == (0, 0)
    assert r.earliest > admin + timedelta(days=days)


# --- RG-07 / RG-31 ------------------------------------------------------------------------------


def test_percentage_ct_ref_02() -> None:
    s = normalise_percentage("10 %", declared_basis="m/v")
    assert (s.value, s.unit, s.basis, s.as_stated) == (Decimal(100), "mg", "par mL", "10 %")
    assert not s.is_ambiguous
    assert normalise_percentage("10 %").is_ambiguous


def test_active_quantity_rg_31() -> None:
    s = normalise_percentage("10 % m/v")
    q = active_quantity(s, Decimal(50), "mL")
    assert (q.as_labelled, q.unit) == (Decimal(5000), "mg")
    with pytest.raises(ValueError):
        active_quantity(normalise_percentage("10 %"), Decimal(50), "mL")
    with pytest.raises(ValueError):
        active_quantity(s, Decimal(50), "mL", active_entity_factor=Decimal("0.9"))


# --- RG-22 --------------------------------------------------------------------------------------


def test_batch_check_ct_alr_03() -> None:
    recalls = [BatchRecall("alr-003", "amm-001", frozenset({"L27-0412", "L27-0413"}), date(2027, 8, 26))]
    hit = check_batch("amm-001", " l27-0412 ", recalls, date(2027, 9, 7))
    assert hit.answer == RECALLED and hit.alert_ids == ("alr-003",)
    miss = check_batch("amm-001", "L27-9999", recalls, date(2027, 9, 7))
    assert miss.answer == NO_KNOWN_RECALL
    assert hit.notice == miss.notice == "Ne constitue pas une authentification."
    assert check_batch("amm-001", "L27-0412", recalls, date(2027, 8, 1)).answer == NO_KNOWN_RECALL
