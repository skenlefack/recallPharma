"""Outils offerts au modèle (D5). Tous lisent par l'API avec le jeton délégué ; aucun n'écrit.

La passerelle complète les arguments que le modèle omet (juridiction de la conversation, dernier jeu de résultats)
et traduit chaque résultat en enregistrements adressables [[identifiant:champ]] pour le contrôle après génération.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import httpx

from recallpharma.domain import copilot as cp

TOOLS_VERSION = "outils-2026.11-2"
_AMM_ID = re.compile(r"amm-[0-9a-z]+")  # forme des identifiants du registre (D5)
WRITE_TOOLS: frozenset[str] = frozenset()  # aucun outil d'écriture n'existe (ENF-SEC-05)


def _fn(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required or []},
        },
    }


_S = {"type": "string"}
TOOL_SPECS: list[dict[str, Any]] = [
    _fn("resolve_substance", "Trouve une substance active par son nom (tolère les fautes).", {"text": _S}, ["text"]),
    _fn(
        "search_authorisations",
        "Liste les AMM publiées d'une juridiction. Total calculé par le registre.",
        {
            "jurisdiction": {**_S, "description": "Code de juridiction ; défaut : celle de la conversation"},
            "substance": {**_S, "description": "Nom de la substance active"},
            "product_name": {**_S, "description": "Nom ou désignation du produit"},
            "species": {**_S, "description": "Espèce cible au pluriel, ex. bovins"},
            "form": {**_S, "description": "Forme pharmaceutique ou partie, ex. injectable"},
            "route": {**_S, "description": "Voie : IM, IV, SC, orale"},
            "status": {**_S, "description": "Statut calculé, ex. valide, suspendue"},
        },
    ),
    _fn(
        "refine_result_set",
        "Filtre le jeu de résultats précédent ; le décompte vient du registre.",
        {
            "result_set_id": {**_S, "description": "Défaut : le dernier jeu de la conversation"},
            "form": _S,
            "route": _S,
            "species": _S,
            "status": _S,
            "withdrawal_species": {**_S, "description": "Espèce du critère de délai d'attente"},
            "withdrawal_commodity": {**_S, "description": "Denrée : lait, viande et abats, œufs, miel"},
            "withdrawal_max_days": {"type": "number", "description": "Délai maximal admis, en jours"},
        },
    ),
    _fn("get_authorisation", "Fiche complète d'une AMM : RCP, délais, sources.", {"ma_id": _S}, ["ma_id"]),
    _fn(
        "get_withdrawal_periods",
        "Délais d'attente d'une AMM, par espèce et denrée.",
        {"ma_id": _S, "species": _S, "commodity": _S},
        ["ma_id"],
    ),
    _fn(
        "compute_withdrawal_end",
        "Date de fin du délai d'attente (RG-21), calculée par le registre.",
        {
            "ma_id": _S,
            "species": _S,
            "commodity": _S,
            "route": _S,
            "last_administration": {**_S, "description": "ISO 8601 avec fuseau, ex. 2027-09-07T14:30:00+01:00"},
            "water_temperature_c": {"type": "number"},
        },
        ["ma_id", "species", "commodity", "last_administration"],
    ),
    _fn("list_alerts", "Alertes publiées (rappels, suspensions) d'une juridiction.", {"jurisdiction": _S}),
    _fn(
        "search_spc_passages",
        "Cherche dans le texte des RCP (indications, contre-indications, posologie, précautions, restrictions). "
        "Renvoie des extraits d'origine avec leur AMM, leur rubrique et leur source.",
        {
            "query": {**_S, "description": "La question ou ses mots clés, dans la langue de l'utilisateur"},
            "jurisdiction": {**_S, "description": "Défaut : celle de la conversation"},
            "product_name": {**_S, "description": "Nom du produit, si la question en nomme un"},
            "ma_ids": {"type": "array", "items": _S, "description": "Identifiants d'AMM (amm-…), si déjà connus"},
        },
        ["query"],
    ),
    _fn(
        "get_spc_section",
        "Une rubrique du RCP d'une AMM, texte d'origine : 3.1 espèces cibles, 3.2 indications, 3.3 contre-indications, "
        "3.4 mises en garde, 3.5 précautions, 3.9 voies et posologie, 3.11 restrictions, 3.12 temps d'attente.",
        {"ma_id": _S, "rubric": {**_S, "description": "Numéro de rubrique, ex. 3.3"}},
        ["ma_id", "rubric"],
    ),
    _fn(
        "compare_jurisdictions",
        "Compare un produit ou une substance entre juridictions : statut, numéro, espèces, délais d'attente.",
        {
            "product_name": _S,
            "substance": {**_S, "description": "Nom de la substance active"},
            "jurisdictions": {"type": "array", "items": _S, "description": "Codes ; défaut : toutes"},
        },
    ),
    _fn(
        "abstain",
        "S'abstenir : diagnostic, choix thérapeutique, médicament humain ou question hors du registre.",
        {"reason": _S},
        ["reason"],
    ),
]
TOOL_NAMES = frozenset(t["function"]["name"] for t in TOOL_SPECS)


class ToolError(Exception):
    def __init__(self, code: str, message: str, extra: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code, self.message, self.extra = code, message, extra or {}

    def as_result(self) -> dict[str, Any]:
        return {"erreur": self.code, "message": self.message, **self.extra}


def _plural(value: Decimal, unit: str) -> str:
    n = int(value) if value == value.to_integral_value() else value
    if n == 0:
        return "zéro (aucun temps d'attente)"
    return f"{n} {unit}{'s' if n > 1 and unit not in ('degré-jour',) and not unit.endswith('s') else ''}"


def withdrawal_text(w: dict[str, Any]) -> str:
    if w["kind"] == "valeur" and w.get("value") is not None:
        return _plural(Decimal(str(w["value"])), w["unit"])
    if w["kind"] == "non renseigné":
        return "non renseigné (ce n'est pas un délai nul)"
    return str(w["kind"])


@dataclass
class Turn:
    """Ce que les outils ont renvoyé pendant le tour : seule base admise pour la réponse (RG-23)."""

    records: dict[str, dict[str, str]] = field(default_factory=dict)
    rows: list[dict[str, Any]] = field(default_factory=list)  # tableau affiché (dernier jeu de résultats)
    banners: list[dict[str, str]] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)
    apart: list[dict[str, str]] = field(default_factory=list)
    elsewhere: list[dict[str, Any]] = field(default_factory=list)
    total: int | None = None
    result_set_id: str | None = None
    lists: int = 0
    calcs: int = 0
    meta: dict[str, dict[str, Any]] = field(default_factory=dict)  # dates de vérification, niveaux, sources
    passages: list[dict[str, Any]] = field(default_factory=list)  # extraits de RCP affichés tels quels, avec source
    comparisons: list[dict[str, Any]] = field(default_factory=list)
    injection_in_data: bool = False  # instruction trouvée dans un texte renvoyé par un outil (CT-COP-08)

    def add_banners(self, banners: list[dict[str, str]]) -> None:
        for b in banners:
            if b not in self.banners:
                self.banners.append(b)

    def add_row_record(self, row: dict[str, Any]) -> None:
        self.records[row["id"]] = {
            "name": row["name"],
            "designation": row["designation"],
            "ma_number": row["ma_number"],
            "status": row["status"],
            "form": row["form"],
            "routes": ", ".join(row["routes"]),
            "species": ", ".join(row["species"]),
            "substances": ", ".join(row["substances"]),
            "strength": ", ".join(row["strengths"]),
            "holder": row["holder"],
            "jurisdiction": row["jurisdiction"],
            "evidence": f"{row['evidence_level']} · {row['evidence_label']}",
            "verified_at": str(row["verified_at"] or "inconnue"),
            "expiry": str(row["expiry_date"] or "illimitée"),
        }
        self.meta[row["id"]] = {
            "verified_at": row["verified_at"],
            "evidence": row["evidence_level"],
            "source": f"{row['source_title']} ({row['source_date']})" if row.get("source_title") else None,
        }
        self.add_banners(row["banners"])


class ToolRunner:
    def __init__(self, client: httpx.Client, token: str, jurisdiction: str, result_set_id: str | None = None) -> None:
        self._client, self._jurisdiction, self.turn = client, jurisdiction, Turn(result_set_id=result_set_id)
        self._headers = {"authorization": f"Bearer {token}"}

    # --- HTTP ---------------------------------------------------------------------------------

    def _call(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            res = self._client.request(method, f"/v1/copilot/tools{path}", headers=self._headers, **kwargs)
        except httpx.HTTPError as exc:
            raise ToolError("tool_unavailable", "Registre injoignable") from exc
        if res.status_code >= 400:
            try:
                problem = res.json()
            except ValueError:
                problem = {}
            code = str(problem.get("type", "")).rsplit("/", 1)[-1] or f"http_{res.status_code}"
            extra = {k: v for k, v in problem.items() if k in ("candidates",)}
            raise ToolError(code, problem.get("detail") or problem.get("title") or "Erreur", extra)
        return res.json()

    def vocabulary(self) -> dict[str, Any]:
        return dict(self._call("GET", "/vocabulary"))

    # --- Outils --------------------------------------------------------------------------------

    def run(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        handler = getattr(self, f"_tool_{name}", None)
        if name not in TOOL_NAMES or name == "abstain" or handler is None:
            raise ToolError("unknown_tool", f"Outil inconnu : {name}")
        result: dict[str, Any] = handler(args)
        return result

    def _tool_resolve_substance(self, args: dict[str, Any]) -> dict[str, Any]:
        return {"candidats": self._call("GET", "/substances", params={"q": str(args.get("text", ""))})}

    def _substance_id(self, text: str) -> str:
        candidates = self._call("GET", "/substances", params={"q": text})
        if not candidates or candidates[0]["score"] < 0.45:
            raise ToolError(
                "substance_unknown",
                f"Aucune substance du registre ne correspond à « {text} »",
                {"candidates": candidates},
            )
        return str(candidates[0]["id"])

    def _list_result(self, data: dict[str, Any]) -> dict[str, Any]:
        t = self.turn
        t.lists += 1
        list_id = f"liste{t.lists}"
        t.result_set_id = data["result_set_id"]
        t.total = data["total"]
        t.rows = data["rows"]
        t.apart = data.get("apart", [])
        t.elsewhere = data.get("elsewhere", [])
        if data.get("notice"):
            t.notices.append(data["notice"])
        for row in data["rows"]:
            t.add_row_record(row)
        t.records[list_id] = {
            "total": str(data["total"]),
            "excluded": str(data.get("excluded", 0)),
            "apart": str(len(data.get("apart", []))),
            "jurisdiction": data["jurisdiction"],
        }
        # Le modèle reçoit une vue compacte : identifiants et champs utiles, 20 lignes au plus.
        return {
            "liste": list_id,
            "result_set_id": data["result_set_id"],
            "total": data["total"],
            "lignes": [
                {
                    k: r[k]
                    for k in ("id", "name", "designation", "status", "form", "routes", "species", "evidence_level")
                }
                for r in data["rows"][:20]
            ],
            "mis_a_part": data.get("apart", []),
            "autres_juridictions": [
                {"id": r["id"], "jurisdiction": r["jurisdiction"]} for r in data.get("elsewhere", [])
            ],
            "avis": data.get("notice"),
        }

    def _tool_search_authorisations(self, args: dict[str, Any]) -> dict[str, Any]:
        body = {k: args.get(k) for k in ("product_name", "species", "form", "route", "status") if args.get(k)}
        body["jurisdiction"] = str(args.get("jurisdiction") or self._jurisdiction)
        if args.get("substance_id"):
            body["substance_id"] = str(args["substance_id"])
        elif args.get("substance"):
            body["substance_id"] = self._substance_id(str(args["substance"]))
        return self._list_result(self._call("POST", "/search", json=body))

    def _tool_refine_result_set(self, args: dict[str, Any]) -> dict[str, Any]:
        rs = args.get("result_set_id") or self.turn.result_set_id
        if not rs:
            raise ToolError("no_result_set", "Aucun jeu de résultats précédent à affiner")
        body: dict[str, Any] = {k: args[k] for k in ("form", "route", "species", "status") if args.get(k)}
        if args.get("withdrawal_commodity") and args.get("withdrawal_max_days") is not None:
            body["withdrawal"] = {
                "species": args.get("withdrawal_species") or args.get("species"),
                "commodity": args["withdrawal_commodity"],
                "max_value": args["withdrawal_max_days"],
                "unit": "jour",
            }
        return self._list_result(self._call("POST", f"/result-sets/{rs}/refine", json=body))

    def _sheet(self, ma_id: str) -> dict[str, Any]:
        sheet: dict[str, Any] = self._call("GET", f"/authorisations/{ma_id}")
        ident, reg, a = sheet["identity"], sheet["regulation"], sheet["assessment"]
        self.turn.records.setdefault(ma_id, {}).update(
            {
                "name": ident["name"],
                "designation": ident["designation"],
                "ma_number": reg["ma_number"],
                "status": a["status"],
                "form": ident["pharmaceutical_form"],
                "routes": ", ".join(ident["routes"]),
                "species": ", ".join(ident["target_species"]),
                "holder": reg["holder"],
                "jurisdiction": sheet["jurisdiction"]["code"],
                "evidence": f"{a['evidence']['level']} · {a['evidence']['label']}",
                "verified_at": str(reg["last_verified_at"]),
                "expiry": str(a["expiry_date"] or "illimitée"),
                "strength": ", ".join(f"{c['substance']} {c['strength_as_stated']}" for c in sheet["components"]),
                "substances": ", ".join(c["substance"] for c in sheet["components"]),
            }
        )
        spc = sheet.get("spc")
        if spc:
            if spc.get("posology"):
                self.turn.records[ma_id]["posology"] = spc["posology"]
            if spc.get("contraindications"):
                self.turn.records[ma_id]["contraindications"] = " ; ".join(spc["contraindications"])
        src = sheet.get("source")
        self.turn.meta[ma_id] = {
            "verified_at": reg["last_verified_at"],
            "evidence": a["evidence"]["level"],
            "source": f"{src['title']} ({src['document_date']})" if src else None,
        }
        self.turn.add_banners(a["banners"])
        return sheet

    def _periods(self, ma_id: str, sheet: dict[str, Any], species: str | None, commodity: str | None) -> list[str]:
        ids = []
        periods = (sheet.get("spc") or {}).get("withdrawal_periods", [])
        for i, w in enumerate(periods, start=1):
            if (species and w["species"] != species) or (commodity and w["commodity"] != commodity):
                continue
            rid = f"{ma_id}#delai{i}"
            self.turn.records[rid] = {
                "species": w["species"],
                "commodity": w["commodity"],
                "route": w["route"] or "toutes voies",
                "value": withdrawal_text(w),
                **({"dose_condition": w["dose_condition"]} if w.get("dose_condition") else {}),
            }
            ids.append(rid)
        return ids

    def _tool_get_authorisation(self, args: dict[str, Any]) -> dict[str, Any]:
        ma_id = str(args.get("ma_id", ""))
        sheet = self._sheet(ma_id)
        delays = self._periods(ma_id, sheet, None, None)
        return {
            "enregistrement": ma_id,
            "champs": sorted(self.turn.records[ma_id]),
            "delais": {d: self.turn.records[d] for d in delays},
            "bandeaux": sheet["assessment"]["banners"],
            "rcp_disponible": sheet.get("spc") is not None,
        }

    def _tool_get_withdrawal_periods(self, args: dict[str, Any]) -> dict[str, Any]:
        ma_id = str(args.get("ma_id", ""))
        sheet = self._sheet(ma_id)
        delays = self._periods(ma_id, sheet, args.get("species"), args.get("commodity"))
        return {"enregistrement": ma_id, "delais": {d: self.turn.records[d] for d in delays}}

    def _tool_compute_withdrawal_end(self, args: dict[str, Any]) -> dict[str, Any]:
        ma_id = str(args.get("ma_id", ""))
        self._sheet(ma_id)
        body = {k: args[k] for k in ("species", "commodity", "route", "last_administration") if args.get(k)}
        if args.get("water_temperature_c") is not None:
            body["water_temperature_c"] = args["water_temperature_c"]
        data = self._call("POST", f"/authorisations/{ma_id}/withdrawal-end", json=body)
        self.turn.calcs += 1
        rid = f"calcul{self.turn.calcs}"
        self.turn.records[rid] = {
            "result": data["message"],
            "earliest": str(data["earliest"] or "aucune date calculée"),
            "formula": str(data["formula"] or "sans calcul"),
            "period": withdrawal_text(data["period"]),
        }
        return {"enregistrement": rid, **self.turn.records[rid]}

    def _tool_list_alerts(self, args: dict[str, Any]) -> dict[str, Any]:
        alerts = self._call("GET", "/alerts", params={"jurisdiction": args.get("jurisdiction") or self._jurisdiction})
        for a in alerts:
            self.turn.records[a["id"]] = {
                "type": a["type"],
                "text": a["text"],
                "published_at": str(a["published_at"]),
                "batches": ", ".join(a["batch_numbers"]) or "aucun lot",
                "closed": str(a["closed_at"] or "en cours"),
            }
            self.turn.meta[a["id"]] = {"verified_at": None, "evidence": None, "source": None}
        return {"alertes": [{"id": a["id"], "type": a["type"], "level": a["level"]} for a in alerts]}

    # --- Texte des RCP et comparaison -------------------------------------------------------------

    def _passage(self, p: dict[str, Any], rid: str) -> dict[str, str]:
        """Un extrait devient un enregistrement : le texte est inséré tel quel, dans sa langue, avec sa source."""
        record = {
            "text": p["text"],
            "rubric": f"{p['rubric']} {p['title']}",
            "language": p["language"],
            "product": p["product"],
            "ma_number": p["ma_number"],
            "source": f"{p['source_title']}, page {p['page']}" if p.get("page") else str(p.get("source_title")),
        }
        self.turn.records[rid] = record
        ma_id = p["authorisation_id"]
        self.turn.meta.setdefault(
            ma_id, {"verified_at": p.get("verified_at"), "evidence": p.get("evidence_level"), "source": None}
        )
        self.turn.add_banners(p.get("banners", []))
        if not any(x["id"] == rid for x in self.turn.passages):
            self.turn.passages.append({"id": rid, "ma_id": ma_id, **record})
        if cp.looks_like_injection(p["text"]):
            self.turn.injection_in_data = True  # donnée suspecte : signalée au journal, jamais suivie
        return record

    def _tool_search_spc_passages(self, args: dict[str, Any]) -> dict[str, Any]:
        params: dict[str, Any] = {
            "q": str(args.get("query") or "")[:300],
            "jurisdiction": str(args.get("jurisdiction") or self._jurisdiction),
        }
        given = args.get("ma_ids") or []
        given = [str(i) for i in ([given] if isinstance(given, str) else given)]
        # Un nom de produit glissé dans ma_ids (faute fréquente du modèle) est traité comme un nom de produit.
        ids = [i for i in given if _AMM_ID.fullmatch(i)]
        names = [i for i in given if not _AMM_ID.fullmatch(i)] + (
            [str(args["product_name"])] if args.get("product_name") else []
        )
        for name in dict.fromkeys(names):
            listing = self._tool_search_authorisations({"product_name": name, "jurisdiction": params["jurisdiction"]})
            ids += [row["id"] for row in listing["lignes"]]
            if not listing["lignes"]:
                return {"passages": [], "avis": f"aucune AMM de « {name} » dans cette juridiction"}
        if ids:
            params["ma_ids"] = ",".join(dict.fromkeys(ids))
        data = self._call("GET", "/spc-passages", params=params)
        found = []
        for p in data["passages"]:
            rid = f"{p['authorisation_id']}#rcp-{p['rubric']}-{p['language']}-{p['rank']}"
            self._passage(p, rid)
            found.append(
                {
                    "id": rid,
                    "ma_id": p["authorisation_id"],
                    "produit": p["product"],
                    "rubrique": p["rubric"],
                    "titre": p["title"],
                    "langue": p["language"],
                    "texte": p["text"],
                }
            )
        return {"passages": found, "mode": data["mode"], "avis": None if found else "aucun passage trouvé"}

    def _tool_get_spc_section(self, args: dict[str, Any]) -> dict[str, Any]:
        ma_id, rubric = str(args.get("ma_id", "")), str(args.get("rubric", "")).strip()
        self._sheet(ma_id)  # statut, bandeaux et niveau de preuve de l'AMM citée (RG-15, RG-26)
        data = self._call("GET", f"/authorisations/{ma_id}/spc/sections/{rubric}")
        rid = f"{ma_id}#rcp-{data['rubric']}-{data['language']}"
        self._passage({**data, "rank": 0}, rid)
        return {"enregistrement": rid, "titre": data["title"], "langue": data["language"], "texte": data["text"]}

    def _tool_compare_jurisdictions(self, args: dict[str, Any]) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if args.get("product_name"):
            body["product_name"] = str(args["product_name"])
        if args.get("substance"):
            body["substance_id"] = self._substance_id(str(args["substance"]))
        codes = args.get("jurisdictions")
        if codes:
            body["jurisdictions"] = [str(c) for c in ([codes] if isinstance(codes, str) else codes)]
        data = self._call("POST", "/compare", json=body)
        t = self.turn
        t.rows, t.total = [], data["total"]
        summary = []
        for i, product in enumerate(data["products"], start=1):
            rid = f"comparaison{i}"
            for row in product["rows"]:
                t.add_row_record(row)
                t.rows.append(row)
                for k, w in enumerate(row["withdrawal"], start=1):
                    t.records[f"{row['id']}#delai{k}"] = {
                        "species": w["species"],
                        "commodity": w["commodity"],
                        "route": w["route"] or "toutes voies",
                        "value": withdrawal_text(w),
                        "jurisdiction": row["jurisdiction"],
                    }
            t.records[rid] = {
                "name": product["name"],
                "present": ", ".join(product["present"]) or "aucune",
                "absent": ", ".join(product["absent"]) or "aucune",
                "differences": ", ".join(product["differences"]) or "aucune différence",
            }
            t.comparisons.append({"id": rid, **product, "rows": [r["id"] for r in product["rows"]]})
            summary.append(
                {
                    "enregistrement": rid,
                    "lignes": [
                        {"id": r["id"], "jurisdiction": r["jurisdiction"], "status": r["status"]}
                        for r in product["rows"]
                    ],
                    **{k: t.records[rid][k] for k in ("present", "absent", "differences")},
                }
            )
        return {"comparaisons": summary, "total": data["total"]}
