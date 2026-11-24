"""Textes de RCP fictifs du jeu A10, rédigés à partir de ses champs structurés (annexe A10 sans texte de RCP).

Chaque rubrique reprend les données de l'AMM (composition, espèces, voies, restrictions, temps d'attente) : le texte
ne contredit jamais les champs validés. Les phrases génériques (indications, mises en garde, posologie) sont des
textes de démonstration, marqués comme tels ; aucune posologie réelle n'est donnée. Langues : celles du RCP.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any

from recallpharma.domain.passages import RUBRICS

SPECIMEN = "SPÉCIMEN, texte fictif"
PAGES = {"1": 1, "2": 1, "3.1": 1, "3.2": 1, "3.3": 1, "3.4": 1, "3.5": 2, "3.9": 2, "3.11": 2, "3.12": 2}
PAGES |= {"6": 3, "7": 3}

SPECIES_EN = {
    "bovins": "cattle",
    "caprins": "goats",
    "chats": "cats",
    "chiens": "dogs",
    "dindes": "turkeys",
    "ovins": "sheep",
    "poissons": "fish",
    "porcins": "pigs",
    "poulets": "chickens",
}
COMMODITY_EN = {"viande et abats": "meat and offal", "chair": "flesh", "lait": "milk", "œufs": "eggs", "miel": "honey"}
ROUTE_FR = {"IM": "voie intramusculaire", "IV": "voie intraveineuse", "SC": "voie sous-cutanée", "orale": "voie orale"}
ROUTE_EN = {"IM": "intramuscular use", "IV": "intravenous use", "SC": "subcutaneous use", "orale": "oral use"}
UNIT_FR = {"jour": ("jour", "jours"), "heure": ("heure", "heures"), "degré-jour": ("degré-jour", "degrés-jours")}
UNIT_EN = {"jour": ("day", "days"), "heure": ("hour", "hours"), "degré-jour": ("degree-day", "degree-days")}
RESTRICTIONS_EN = {
    "Ne pas utiliser chez les oiseaux pondeurs d'œufs destinés à la consommation.": (
        "Do not use in birds producing eggs for human consumption."
    ),
    "Ne pas utiliser chez les femelles laitières, y compris pendant le tarissement.": (
        "Do not use in lactating animals, including during the dry period."
    ),
    "Ne pas utiliser chez les poules pondeuses dont les œufs sont destinés à la consommation humaine.": (
        "Do not use in laying hens producing eggs for human consumption."
    ),
    "Ne pas utiliser chez les femelles productrices de lait destiné à la consommation humaine.": (
        "Do not use in animals producing milk for human consumption."
    ),
    "Ne pas administrer aux animaux producteurs de denrées alimentaires.": (
        "Do not administer to food-producing animals."
    ),
}
ANTIPARASITIC = {"ivermectine", "albendazole", "lévamisole", "fenbendazole", "praziquantel", "toltrazuril"}
ANTI_INFLAMMATORY = {"méloxicam", "flunixine"}


@dataclass(frozen=True, slots=True)
class SectionText:
    rubric: str
    language: str
    title: str
    text: str
    page: int


def inn_en(name: str) -> str:
    """Dénomination commune en anglais : sans accents, « -ine » final abrégé sauf pour les tétracyclines."""
    plain = "".join(c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c))
    return plain if plain.endswith("cycline") or not plain.endswith("ine") else plain[:-1]


def _join(items: list[str], last: str) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} {last} {items[-1]}"


def _first_upper(text: str) -> str:
    return text[:1].upper() + text[1:]


def _period(w: dict[str, Any], language: str) -> str:
    en = language == "en"
    species = SPECIES_EN.get(w["species"], w["species"]) if en else w["species"]
    commodity = COMMODITY_EN.get(w["commodity"], w["commodity"]) if en else w["commodity"]
    head = f"{_first_upper(species)}, {commodity}"
    if w.get("route"):
        head += f" ({(ROUTE_EN if en else ROUTE_FR).get(w['route'], w['route'])})"
    if w.get("dose_condition"):
        head += f", {w['dose_condition']}"
    if w["kind"] == "valeur" and w.get("value") is not None:
        n = w["value"]
        one, many = (UNIT_EN if en else UNIT_FR).get(w["unit"], (w["unit"], w["unit"]))
        value = ("zero days" if en else "zéro jour") if n == 0 else f"{n:g} {one if n == 1 else many}"
    elif w["kind"] == "interdit":
        value = "not authorised for use" if en else "utilisation interdite"
    elif w["kind"] == "non renseigné":
        value = "not stated" if en else "non renseigné"
    else:
        value = w["kind"]
    return f"{head} : {value}." if not en else f"{head}: {value}."


def _class(product: dict[str, Any], substances: dict[str, dict[str, Any]]) -> str:
    if product["product_type"] == "immunologique":
        return "vaccin"
    names = {i["inn_name"] for i in product["ingredients"]}
    if any(substances.get(i["substance_id"], {}).get("is_antimicrobial") for i in product["ingredients"]):
        return "antibiotique"
    if names & ANTIPARASITIC:
        return "antiparasitaire"
    if names & ANTI_INFLAMMATORY:
        return "anti-inflammatoire"
    return "autre"


def _fr(a: dict[str, Any], p: dict[str, Any], kind: str, subs: list[str], critical: bool) -> dict[str, str]:
    species = p["target_species"]
    actives = _join(subs, "et")
    restrictions = [r["text"] for r in a["spc"].get("restrictions", [])]
    indications = {
        "antibiotique": "Traitement des infections causées par des bactéries sensibles à la substance active "
        f"({actives}).",
        "antiparasitaire": "Traitement des infestations par des parasites sensibles à la substance active "
        f"({actives}).",
        "anti-inflammatoire": "Réduction de l'inflammation et de la douleur.",
        "vaccin": "Immunisation active pour réduire les signes cliniques et la mortalité dus à la maladie visée.",
        "autre": "Indications de démonstration.",
    }[kind]
    warnings = (
        "L'utilisation du médicament doit reposer sur l'identification de la bactérie et sur un antibiogramme ; "
        "elle tient compte des politiques officielles et locales d'utilisation des antimicrobiens."
        if kind == "antibiotique"
        else "Aucune mise en garde particulière pour ce texte de démonstration."
    )
    if critical:
        warnings += " Cette substance est d'importance critique : la réserver aux cas où aucune autre ne convient."
    contra = ["Ne pas utiliser en cas d'hypersensibilité à la substance active ou à l'un des excipients."]
    if kind == "antibiotique":
        contra.append("Ne pas utiliser en cas de résistance connue à la substance active.")
    contra += a["spc"].get("contraindications", [])
    routes = _join([ROUTE_FR.get(r, r) for r in p["routes"]], "ou")
    periods = [_period(w, "fr") for w in a["spc"]["withdrawal_periods"]]
    return {
        "1": f"{p['name']}, {p['designation']} ({SPECIMEN}).",
        "2": "Substance(s) active(s) : "
        + "; ".join(f"{i['inn_name']} {i['strength_as_stated']}" for i in p["ingredients"])
        + ". Excipients : voir la liste complète (texte de démonstration).",
        "3.1": _first_upper(_join(species, "et")) + ".",
        "3.2": indications,
        "3.3": " ".join(contra),
        "3.4": warnings,
        "3.5": "Les personnes présentant une hypersensibilité connue à la substance active doivent éviter tout contact "
        "avec le médicament. En cas d'auto-injection ou d'ingestion accidentelle, demander conseil à un médecin et lui "
        "montrer la notice.",
        "3.9": f"Administration par {routes}. Posologie : texte de démonstration, sans dose réelle ; se reporter à la "
        "prescription du vétérinaire.",
        "3.11": " ".join(restrictions) if restrictions else "Aucune restriction particulière.",
        "3.12": " ".join(periods) if periods else "Sans objet.",
        "6": f"{a['holder']}.",
        "7": f"{a['ma_number']}.",
    }


def _en(a: dict[str, Any], p: dict[str, Any], kind: str, subs: list[str], critical: bool) -> dict[str, str]:
    species = [SPECIES_EN.get(s, s) for s in p["target_species"]]
    actives = _join([inn_en(s) for s in subs], "and")
    restrictions = [RESTRICTIONS_EN.get(r["text"], r["text"]) for r in a["spc"].get("restrictions", [])]
    indications = {
        "antibiotique": f"Treatment of infections caused by bacteria susceptible to {actives}.",
        "antiparasitaire": f"Treatment of infestations by parasites susceptible to {actives}.",
        "anti-inflammatoire": "Reduction of inflammation and pain.",
        "vaccin": "Active immunisation to reduce clinical signs and mortality caused by the target disease.",
        "autre": "Demonstration indications.",
    }[kind]
    warnings = (
        "Use of the product should be based on identification and susceptibility testing of the target bacteria, "
        "taking into account official and local antimicrobial policies."
        if kind == "antibiotique"
        else "No special warnings for this demonstration text."
    )
    if critical:
        warnings += " This substance is critically important: reserve it for cases where no other is suitable."
    contra = ["Do not use in cases of hypersensitivity to the active substance or to any of the excipients."]
    if kind == "antibiotique":
        contra.append("Do not use in cases of known resistance to the active substance.")
    routes = _join([ROUTE_EN.get(r, r) for r in p["routes"]], "or")
    periods = [_period(w, "en") for w in a["spc"]["withdrawal_periods"]]
    return {
        "1": f"{p['name']} (specimen, fictitious text).",
        "2": "Active substance(s): "
        + "; ".join(f"{inn_en(i['inn_name'])} {i['strength_as_stated']}" for i in p["ingredients"])
        + ". Excipients: see the full list (demonstration text).",
        "3.1": _first_upper(_join(species, "and")) + ".",
        "3.2": indications,
        "3.3": " ".join(contra),
        "3.4": warnings,
        "3.5": "People with known hypersensitivity to the active substance should avoid contact with the product. "
        "In case of accidental self-injection or ingestion, seek medical advice and show the package leaflet to the "
        "physician.",
        "3.9": f"For {routes}. Dosage: demonstration text without a real dose; follow the veterinarian's prescription.",
        "3.11": " ".join(restrictions) if restrictions else "No special restrictions.",
        "3.12": " ".join(periods) if periods else "Not applicable.",
        "6": f"{a['holder']}.",
        "7": f"{a['ma_number']}.",
    }


def spc_sections(
    authorisation: dict[str, Any], product: dict[str, Any], substances: dict[str, dict[str, Any]]
) -> list[SectionText]:
    """Rubriques du RCP d'une AMM du jeu A10, dans chacune de ses langues ; vide si l'AMM n'a pas de RCP."""
    if not authorisation.get("spc"):
        return []
    kind = _class(product, substances)
    subs = [i["inn_name"] for i in product["ingredients"]] or [product["designation"]]
    critical = any(
        "critique" in (substances.get(i["substance_id"], {}).get("who_category") or "") for i in product["ingredients"]
    )
    out: list[SectionText] = []
    for language in authorisation["spc"]["languages"]:
        texts = (_en if language == "en" else _fr)(authorisation, product, kind, subs, critical)
        for rubric in RUBRICS:
            title = RUBRICS[rubric][1 if language == "en" else 0]
            out.append(SectionText(rubric, language, title, texts[rubric], PAGES[rubric]))
    return out
