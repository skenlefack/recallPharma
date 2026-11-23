"""Publication atomique d'une proposition validée dans le référentiel (M02).

Une seule version publiée par AMM ; la proposition précédente passe « archivée ». Les événements réglementaires
sont ajoutés, jamais supprimés. Un changement de forme ou de composition crée un nouveau produit (RG-02).
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from recallpharma.db import models as m
from recallpharma.domain.curation import ProposalState, canonical_number, normalise_text
from recallpharma.domain.identifiers import normalise_ma_number


def _d(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _dec(value: Any) -> Decimal | None:
    return Decimal(str(value)) if value is not None and value != "" else None


def _event_key(e: dict[str, Any]) -> tuple[str, str, str]:
    return (e["type"], str(e["decision_date"]), str(e["effective_date"]))


def payload_from_authorisation(row: m.Authorisation) -> dict[str, Any]:
    """État publié d'une AMM, dans le format d'une proposition (point de départ d'une mise à jour)."""
    p = row.product
    spc = row.spc_versions[-1] if row.spc_versions else None
    return {
        "jurisdiction": row.jurisdiction_code,
        "ma_number": row.ma_number,
        "procedure": row.procedure,
        "holder": row.holder,
        "manufacturer": row.manufacturer,
        "dispensing_condition": row.dispensing_condition,
        "grant_date": row.grant_date.isoformat(),
        "expiry_date": row.expiry_date.isoformat() if row.expiry_date else None,
        "renewal_pending": row.renewal_pending,
        "events": [
            {
                "type": e.type,
                "decision_date": e.decision_date.isoformat(),
                "effective_date": e.effective_date.isoformat(),
                "end_date": e.end_date.isoformat() if e.end_date else None,
                "reason": e.reason,
                "new_expiry_date": e.new_expiry_date.isoformat() if e.new_expiry_date else None,
            }
            for e in row.events
        ],
        "product": {
            "id": p.id,
            "name": p.name,
            "designation": p.designation,
            "pharmaceutical_form": p.pharmaceutical_form,
            "product_type": p.product_type,
            "routes": list(p.routes),
            "target_species": list(p.target_species),
            "components": [
                {
                    "substance_id": c.substance_id,
                    "strength_as_stated": c.strength_as_stated,
                    "strength_value": str(c.strength_value) if c.strength_value is not None else None,
                    "strength_unit": c.strength_unit,
                    "strength_basis": c.strength_basis,
                }
                for c in p.components
            ],
        },
        "spc": spc_payload(spc) if spc else None,
    }


def removed_events(row: m.Authorisation, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Événements publiés absents de la proposition : interdit, l'historique est en ajout seul."""
    kept = {_event_key(e) for e in payload.get("events") or []}
    published = payload_from_authorisation(row)["events"]
    return [e for e in published if _event_key(e) not in kept]


def _identity(form: str, components: list[dict[str, Any]]) -> tuple[str, tuple[tuple[str, str], ...]]:
    return (
        normalise_text(form),
        tuple(sorted((str(c["substance_id"]), normalise_text(c["strength_as_stated"])) for c in components)),
    )


def _product(session: Session, data: dict[str, Any]) -> m.Product:
    existing = session.get(m.Product, data["id"]) if data.get("id") else None
    wanted = _identity(data["pharmaceutical_form"], data["components"])
    if (
        existing is not None
        and _identity(
            existing.pharmaceutical_form,
            [{"substance_id": c.substance_id, "strength_as_stated": c.strength_as_stated} for c in existing.components],
        )
        == wanted
    ):
        product = existing  # même produit : dénomination, voies et espèces se mettent à jour
    else:
        product = m.Product(id=f"prd-{uuid.uuid4().hex[:10]}", pharmaceutical_form=data["pharmaceutical_form"])
        product.components = [
            m.ProductComponent(
                substance_id=c["substance_id"],
                strength_as_stated=c["strength_as_stated"],
                strength_value=_dec(c.get("strength_value")),
                strength_unit=c.get("strength_unit"),
                strength_basis=c.get("strength_basis"),
                is_ambiguous=False,  # RG-07 : une teneur ambiguë n'arrive jamais jusqu'ici
            )
            for c in data["components"]
        ]
        session.add(product)
    product.name = data["name"]
    product.designation = data["designation"]
    product.product_type = data.get("product_type") or "pharmaceutique"
    product.routes = list(data.get("routes") or [])
    product.target_species = list(data.get("target_species") or [])
    return product


def _spc_changed(current: m.SpcVersion | None, spc: dict[str, Any]) -> bool:
    if current is None:
        return True

    def canon(d: dict[str, Any]) -> dict[str, Any]:
        periods = [{**w, "value": canonical_number(w.get("value"))} for w in d.get("withdrawal_periods") or []]
        return {**{k: v for k, v in d.items() if k != "version_label"}, "withdrawal_periods": periods}

    return canon(spc) != canon(spc_payload(current))


def spc_payload(spc: m.SpcVersion) -> dict[str, Any]:
    return {
        "languages": list(spc.languages),
        "posology": spc.posology,
        "contraindications": list(spc.contraindications),
        "restrictions": list(spc.restrictions),
        "withdrawal_periods": [
            {
                "species": w.species,
                "commodity": w.commodity,
                "route": w.route,
                "dose_condition": w.dose_condition,
                "kind": w.kind,
                "value": str(w.value) if w.value is not None else None,
                "unit": w.unit,
                "spc_text": w.spc_text,
            }
            for w in spc.withdrawal_periods
        ],
    }


def publish(session: Session, proposal: m.Proposal, today: date) -> m.Authorisation:
    data = proposal.payload
    product = _product(session, data["product"])
    session.flush()

    row = session.get(m.Authorisation, proposal.authorisation_id) if proposal.authorisation_id else None
    if row is None:
        row = m.Authorisation(id=f"amm-{uuid.uuid4().hex[:10]}")
        session.add(row)
    row.jurisdiction_code = data["jurisdiction"]
    row.ma_number = data["ma_number"]
    row.ma_number_normalized = normalise_ma_number(data["ma_number"])
    row.product_id = product.id
    row.procedure = data.get("procedure") or "nationale"
    row.holder = data["holder"]
    row.manufacturer = data.get("manufacturer")
    row.dispensing_condition = data.get("dispensing_condition")
    row.grant_date = date.fromisoformat(data["grant_date"])
    row.expiry_date = _d(data.get("expiry_date"))
    row.expiry_is_computed = data.get("expiry_date") is None
    row.renewal_pending = bool(data.get("renewal_pending"))
    row.source_document_id = proposal.provenance["ma_number"]["document_id"]
    row.validations = 2
    row.last_verified_at = today
    row.dispute_open = False
    row.publication_state = ProposalState.PUBLISHED.value
    session.flush()

    known = {(e.type, e.decision_date.isoformat(), e.effective_date.isoformat()) for e in row.events}
    for e in data.get("events") or []:
        if _event_key(e) in known:
            continue
        session.add(
            m.RegulatoryEvent(
                authorisation_id=row.id,
                type=e["type"],
                decision_date=date.fromisoformat(e["decision_date"]),
                effective_date=date.fromisoformat(e["effective_date"]),
                end_date=_d(e.get("end_date")),
                reason=e.get("reason"),
                new_expiry_date=_d(e.get("new_expiry_date")),
            )
        )

    spc = data.get("spc")
    current = row.spc_versions[-1] if row.spc_versions else None
    if spc and _spc_changed(current, spc):
        version = m.SpcVersion(
            authorisation_id=row.id,
            version_label=f"v{len(row.spc_versions) + 1}",
            languages=list(spc.get("languages") or []),
            posology=spc.get("posology"),
            contraindications=list(spc.get("contraindications") or []),
            restrictions=list(spc.get("restrictions") or []),
            proposal_id=proposal.id,
        )
        version.withdrawal_periods = [
            m.WithdrawalPeriod(
                species=w["species"],
                commodity=w["commodity"],
                route=w.get("route"),
                dose_condition=w.get("dose_condition"),
                kind=w["kind"],
                value=_dec(w.get("value")),
                unit=w.get("unit"),
                spc_text=w.get("spc_text"),
            )
            for w in spc.get("withdrawal_periods") or []
        ]
        session.add(version)

    # Une seule version publiée par AMM : la précédente passe à l'historique.
    session.execute(
        update(m.Proposal)
        .where(
            m.Proposal.authorisation_id == row.id,
            m.Proposal.state == ProposalState.PUBLISHED.value,
            m.Proposal.id != proposal.id,
        )
        .values(state=ProposalState.ARCHIVED.value)
    )
    proposal.authorisation_id = row.id
    session.flush()
    session.expire(row)
    return session.scalars(select(m.Authorisation).where(m.Authorisation.id == row.id)).one()
