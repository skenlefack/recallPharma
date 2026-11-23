"""Passage des lignes de base aux objets du domaine, pour que les règles restent pures."""

from __future__ import annotations

from recallpharma.db import models as m
from recallpharma.domain import model as d
from recallpharma.domain.withdrawal import WithdrawalKind, WithdrawalPeriod, WithdrawalUnit


def jurisdiction(row: m.Jurisdiction) -> d.Jurisdiction:
    return d.Jurisdiction(
        code=row.code,
        name=row.name,
        kind=row.kind,
        timezone=row.timezone,
        validity_years=row.validity_years,
        banned_list_communicated="non communiquée" not in row.banned_list_status,
        banned_substances=frozenset(row.banned_substances),
        members=tuple(row.members),
    )


def substance(row: m.Substance) -> d.Substance:
    return d.Substance(
        id=row.id,
        inn_name=row.inn_name,
        atcvet_code=row.atcvet_code,
        is_antimicrobial=row.is_antimicrobial,
        who_category=d.WhoCategory(row.who_category) if row.who_category else None,
        woah_category=row.woah_category,
        codex_rmr=row.codex_rmr,
    )


def authorisation(row: m.Authorisation) -> d.MarketingAuthorisation:
    src = row.source
    return d.MarketingAuthorisation(
        id=row.id,
        jurisdiction=row.jurisdiction_code,
        ma_number=row.ma_number,
        product_id=row.product_id,
        procedure=row.procedure,
        grant_date=row.grant_date,
        expiry_date=row.expiry_date,
        expiry_is_computed=row.expiry_is_computed,
        source=d.Source(
            nature=d.SourceNature(src.nature),
            title=src.title,
            document_date=src.document_date,
            latest_edition=src.latest_edition,
        )
        if src
        else None,
        validations=row.validations,
        last_verified_at=row.last_verified_at,
        dispute_open=row.dispute_open,
        renewal_pending=row.renewal_pending,
        events=tuple(
            d.RegulatoryEvent(
                type=d.EventType(e.type),
                decision_date=e.decision_date,
                effective_date=e.effective_date,
                end_date=e.end_date,
                reason=e.reason,
                new_expiry_date=e.new_expiry_date,
                known_at=e.recorded_at.date(),
            )
            for e in row.events
        ),
    )


def withdrawal(row: m.WithdrawalPeriod) -> WithdrawalPeriod:
    return WithdrawalPeriod(
        species=row.species,
        commodity=row.commodity,
        kind=WithdrawalKind(row.kind),
        value=row.value,
        unit=WithdrawalUnit(row.unit) if row.unit else None,
        route=row.route,
        dose_condition=row.dose_condition,
        spc_text=row.spc_text,
    )
