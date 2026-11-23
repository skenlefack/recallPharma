"""Charge le jeu fictif A10 en base : `python -m recallpharma.seed.load_db`.

Refuse de s'exécuter sur une base qui contient déjà des AMM, pour ne jamais mêler démo et données réelles.
"""

from __future__ import annotations

import sys
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from recallpharma.db import models as m
from recallpharma.db.audit import record
from recallpharma.db.session import session_factory
from recallpharma.domain.identifiers import normalise_ma_number
from recallpharma.seed.a10 import DEFAULT_PATH, load


def _source_key(src: dict[str, Any]) -> tuple[str, str, str, bool]:
    return (src["nature"], src["title"], src["document_date"], src["latest_edition"])


def load_a10(session: Session) -> int:
    if session.scalar(select(func.count()).select_from(m.Authorisation)):
        raise RuntimeError("la base contient déjà des AMM : chargement du jeu de démonstration refusé")
    raw = load(DEFAULT_PATH).raw

    for j in raw["jurisdictions"]:
        session.add(
            m.Jurisdiction(
                code=j["code"],
                name=j["name"],
                kind=j["type"],
                timezone=j["timezone"],
                validity_years=j.get("validity_years"),
                members=j.get("members", []),
                banned_list_status=j.get("banned_list_status", "liste nationale non communiquée"),
                banned_substances=j.get("banned_substances", []),
            )
        )
    for acc in raw["accounts"]:
        session.add(
            m.Account(
                id=acc["id"],
                login=acc["login"],
                display_name=f"{acc['role']} ({acc['id']})",
                roles=[acc["role"]],
            )
        )
    for o in raw["organisations"]:
        session.add(m.Organisation(id=o["id"], name=o["name"], country=o.get("country")))
    for s in raw["substances"]:
        session.add(
            m.Substance(
                id=s["id"],
                inn_name=s["inn_name"],
                atcvet_code=s.get("atcvet_code"),
                is_antimicrobial=s.get("is_antimicrobial", False),
                who_category=s.get("who_category"),
                woah_category=s.get("woah_category"),
                codex_rmr=s.get("codex_rmr", False),
            )
        )
    session.flush()

    for p in raw["products"]:
        product = m.Product(
            id=p["id"],
            name=p["name"],
            designation=p["designation"],
            pharmaceutical_form=p["pharmaceutical_form"],
            product_type=p["product_type"],
            routes=p.get("routes", []),
            target_species=p.get("target_species", []),
        )
        product.components = [
            m.ProductComponent(
                substance_id=i["substance_id"],
                strength_as_stated=i["strength_as_stated"],
                strength_value=Decimal(str(i["strength_value"])) if i.get("strength_value") is not None else None,
                strength_unit=i.get("strength_unit"),
                strength_basis=i.get("strength_basis"),
                is_ambiguous=i["is_ambiguous"],
            )
            for i in p["ingredients"]
        ]
        session.add(product)
    session.flush()

    sources: dict[tuple[str, str, str, bool], m.SourceDocument] = {}
    for a in raw["authorisations"]:
        src = a["source"]
        source = None
        if src:
            key = _source_key(src)
            if key not in sources:
                sources[key] = m.SourceDocument(
                    nature=src["nature"],
                    title=src["title"],
                    document_date=date.fromisoformat(src["document_date"]),
                    latest_edition=src["latest_edition"],
                )
                session.add(sources[key])
            source = sources[key]
        ma = m.Authorisation(
            id=a["id"],
            jurisdiction_code=a["jurisdiction"],
            ma_number=a["ma_number"],
            ma_number_normalized=normalise_ma_number(a["ma_number"]),
            product_id=a["product_id"],
            procedure=a["procedure"],
            holder=a["holder"],
            manufacturer=a.get("manufacturer"),
            dispensing_condition=a.get("dispensing_condition"),
            grant_date=date.fromisoformat(a["grant_date"]),
            expiry_date=date.fromisoformat(a["expiry_date"]) if a.get("expiry_date") else None,
            expiry_is_computed=a["expiry_is_computed"],
            source=source,
            validations=a["validations"],
            last_verified_at=date.fromisoformat(a["last_verified_at"]),
            dispute_open=a["dispute_open"],
            renewal_pending=a.get("renewal_pending", False),
            publication_state="publiée" if a["expected"]["published"] else "proposée",
        )
        ma.events = [
            m.RegulatoryEvent(
                type=e["type"],
                decision_date=date.fromisoformat(e["decision_date"]),
                effective_date=date.fromisoformat(e["effective_date"]),
                end_date=date.fromisoformat(e["end_date"]) if e.get("end_date") else None,
                reason=e.get("reason") or ("non communiqué" if e["type"] != "octroi" else None),
                # Temps de connaissance : la décision, faute d'historique réel de saisie.
                recorded_at=datetime.combine(date.fromisoformat(e["decision_date"]), time.min, tzinfo=UTC),
            )
            for e in a["events"]
        ]
        if "spc" in a:
            spc = a["spc"]
            version = m.SpcVersion(
                version_label=spc["version_label"],
                languages=spc["languages"],
                restrictions=spc.get("restrictions", []),
            )
            version.withdrawal_periods = [
                m.WithdrawalPeriod(
                    species=w["species"],
                    commodity=w["commodity"],
                    route=w.get("route"),
                    dose_condition=w.get("dose_condition"),
                    kind=w["kind"],
                    value=Decimal(str(w["value"])) if w.get("value") is not None else None,
                    unit=w.get("unit"),
                )
                for w in spc["withdrawal_periods"]
            ]
            ma.spc_versions = [version]
        session.add(ma)
    session.flush()

    for al in raw["alerts"]:
        session.add(
            m.SafetyNotice(
                id=al["id"],
                type=al["type"],
                level=al["level"],
                jurisdictions=al["jurisdictions"],
                authorisation_ids=al.get("ma_ids", []),
                batch_numbers=al.get("batch_numbers", []),
                unlisted_product=al.get("unlisted_product"),
                published_at=date.fromisoformat(al["published_at"]),
                closed_at=date.fromisoformat(al["closed_at"]) if al.get("closed_at") else None,
                text=al["text"],
            )
        )
    count = len(raw["authorisations"])
    record(
        session,
        actor="système:amorçage",
        action="import",
        object_type="jeu_amorcage",
        object_id="A10",
        after={"authorisations": count, "alerts": len(raw["alerts"])},
        reason="Chargement du jeu fictif A10 pour démonstration",
    )
    return count


def main() -> None:
    with session_factory()() as session, session.begin():
        count = load_a10(session)
    print(f"{count} AMM fictives chargées.", file=sys.stderr)


if __name__ == "__main__":
    main()
