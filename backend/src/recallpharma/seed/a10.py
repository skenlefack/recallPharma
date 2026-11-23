"""Lecture du jeu d'amorçage fictif A10 en objets du domaine (tests de référence, démonstration)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from recallpharma.domain.batch import BatchRecall
from recallpharma.domain.model import (
    EventType,
    Jurisdiction,
    MarketingAuthorisation,
    RegulatoryEvent,
    Source,
    SourceNature,
    Substance,
    WhoCategory,
)
from recallpharma.domain.withdrawal import WithdrawalKind, WithdrawalPeriod, WithdrawalUnit

DEFAULT_PATH = Path(__file__).with_name("A10-jeu-amorcage.json")


def _d(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


@dataclass(frozen=True, slots=True)
class SeedSet:
    reference_date: date
    jurisdictions: dict[str, Jurisdiction]
    substances: dict[str, Substance]
    products: dict[str, dict[str, Any]]
    authorisations: list[MarketingAuthorisation]
    withdrawal_periods: dict[str, list[WithdrawalPeriod]]  # par identifiant d'AMM
    recalls: list[BatchRecall]
    raw: dict[str, Any]

    def substances_of(self, product_id: str) -> list[Substance]:
        return [self.substances[i["substance_id"]] for i in self.products[product_id]["ingredients"]]


def _jurisdiction(j: dict[str, Any]) -> Jurisdiction:
    return Jurisdiction(
        code=j["code"],
        name=j["name"],
        kind=j["type"],
        timezone=j["timezone"],
        validity_years=j.get("validity_years"),
        banned_list_communicated="non communiquée" not in j.get("banned_list_status", "non communiquée"),
        banned_substances=frozenset(j.get("banned_substances", [])),
        members=tuple(j.get("members", [])),
    )


def _substance(s: dict[str, Any]) -> Substance:
    return Substance(
        id=s["id"],
        inn_name=s["inn_name"],
        atcvet_code=s.get("atcvet_code"),
        is_antimicrobial=s.get("is_antimicrobial", False),
        who_category=WhoCategory(s["who_category"]) if s.get("who_category") else None,
        woah_category=s.get("woah_category"),
        codex_rmr=s.get("codex_rmr", False),
    )


def _authorisation(a: dict[str, Any]) -> MarketingAuthorisation:
    src = a["source"]
    return MarketingAuthorisation(
        id=a["id"],
        jurisdiction=a["jurisdiction"],
        ma_number=a["ma_number"],
        product_id=a["product_id"],
        procedure=a["procedure"],
        grant_date=date.fromisoformat(a["grant_date"]),
        expiry_date=_d(a.get("expiry_date")),
        expiry_is_computed=a["expiry_is_computed"],
        source=Source(
            nature=SourceNature(src["nature"]),
            title=src["title"],
            document_date=date.fromisoformat(src["document_date"]),
            latest_edition=src["latest_edition"],
        )
        if src
        else None,
        validations=a["validations"],
        last_verified_at=date.fromisoformat(a["last_verified_at"]),
        dispute_open=a["dispute_open"],
        renewal_pending=a.get("renewal_pending", False),
        events=tuple(
            RegulatoryEvent(
                type=EventType(e["type"]),
                decision_date=date.fromisoformat(e["decision_date"]),
                effective_date=date.fromisoformat(e["effective_date"]),
                end_date=_d(e.get("end_date")),
                reason=e.get("reason"),
            )
            for e in a["events"]
        ),
    )


def _withdrawal(w: dict[str, Any]) -> WithdrawalPeriod:
    return WithdrawalPeriod(
        species=w["species"],
        commodity=w["commodity"],
        kind=WithdrawalKind(w["kind"]),
        value=Decimal(str(w["value"])) if w.get("value") is not None else None,
        unit=WithdrawalUnit(w["unit"]) if w.get("unit") else None,
        route=w.get("route"),
        dose_condition=w.get("dose_condition"),
    )


def load(path: Path = DEFAULT_PATH) -> SeedSet:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return SeedSet(
        reference_date=date.fromisoformat(raw["meta"]["reference_date"]),
        jurisdictions={j["code"]: _jurisdiction(j) for j in raw["jurisdictions"]},
        substances={s["id"]: _substance(s) for s in raw["substances"]},
        products={p["id"]: p for p in raw["products"]},
        authorisations=[_authorisation(a) for a in raw["authorisations"]],
        withdrawal_periods={
            a["id"]: [_withdrawal(w) for w in a["spc"]["withdrawal_periods"]]
            for a in raw["authorisations"]
            if "spc" in a
        },
        recalls=[
            BatchRecall(
                alert_id=al["id"],
                ma_id=ma_id,
                batch_numbers=frozenset(al["batch_numbers"]),
                published_at=date.fromisoformat(al["published_at"]),
                closed_at=_d(al.get("closed_at")),
            )
            for al in raw["alerts"]
            if al.get("batch_numbers")
            for ma_id in al.get("ma_ids", [])
        ],
        raw=raw,
    )
