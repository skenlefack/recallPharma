"""Recherche de passages de RCP (D6) : 100 questions et leurs rubriques pertinentes ; seuil : rappel à 10 ≥ 0,90.

Usage (base chargée et indexée, modèle de plongements servi) :
    uv run python -m recallpharma.evaluation.passages_eval --build      # régénère le jeu de référence
    uv run python -m recallpharma.evaluation.passages_eval [--full-text] [--json rapport.json]

Un tiers des questions est en anglais et porte sur des RCP rédigés en français seulement : le plein texte n'y trouve
rien, c'est la part que les plongements multilingues doivent couvrir. Un passage est pertinent s'il appartient à une
rubrique attendue (AMM et rubrique), dans l'une ou l'autre langue du RCP. Questions de deux sortes :
- produit connu : l'outil reçoit l'AMM (ma_ids), comme le fait le Copilot après sa recherche ;
- registre : aucune AMM fournie, toutes les rubriques pertinentes de la juridiction sont attendues.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import random
import sys
from typing import Any

from recallpharma.domain.passages import recall_at

REFERENCE = pathlib.Path(__file__).with_name("spc-passages-reference.json")
VERSION = "rcp-2026.11-100"
THRESHOLD = 0.90
SEED = 20261124

ASK_FR = {
    "2": ("Quelle est la composition de {p} ?", "Quelle substance active contient {p} ?"),
    "3.1": ("Pour quelles espèces {p} est-il destiné ?", "Quels animaux peut-on traiter avec {p} ?"),
    "3.2": ("À quoi sert {p} ?", "Quelles sont les indications de {p} ?"),
    "3.3": ("Quelles sont les contre-indications de {p} ?", "Dans quels cas ne faut-il pas utiliser {p} ?"),
    "3.4": ("Quelles sont les mises en garde pour {p} ?",),
    "3.5": ("Quelles précautions doit prendre la personne qui administre {p} ?",),
    "3.9": ("Quelle est la posologie de {p} ?", "Comment administrer {p} ?"),
    "3.11": ("Y a-t-il des restrictions d'utilisation pour {p} ?",),
    "3.12": ("Quel est le temps d'attente de {p} ?", "Combien de temps attendre avant l'abattage après {p} ?"),
}
ASK_EN = {
    "2": ("What does {p} contain?",),
    "3.1": ("Which species is {p} intended for?",),
    "3.2": ("What is {p} used for?",),
    "3.3": ("What are the contraindications of {p}?", "When should {p} not be used?"),
    "3.4": ("Are there special warnings for {p}?",),
    "3.5": ("What precautions should the person giving {p} take?",),
    "3.9": ("What is the dosage of {p}?", "How is {p} administered?"),
    "3.11": ("Are there restrictions on the use of {p}?",),
    "3.12": ("What is the withdrawal period of {p}?", "How long before slaughter after treating with {p}?"),
}
# Questions sur le registre entier : (texte, langue, rubrique, mots dont l'un doit figurer dans la rubrique).
REGISTRY = (
    ("Quels médicaments ne faut-il pas utiliser chez les poules pondeuses ?", "fr", "3.11", ("pondeu",)),
    ("Which medicines must not be used in laying hens?", "en", "3.11", ("pondeu",)),
    ("Quels produits sont interdits chez les femelles laitières ?", "fr", "3.11", ("lait",)),
    ("Which products cannot be used in dairy animals?", "en", "3.11", ("lait",)),
    ("Quels produits ne doivent pas être donnés aux animaux producteurs de denrées ?", "fr", "3.11", ("denrées",)),
    ("Which products must not be given to food-producing animals?", "en", "3.11", ("denrées",)),
    ("Quelles substances sont d'importance critique ?", "fr", "3.4", ("importance critique",)),
    ("Which substances are critically important antimicrobials?", "en", "3.4", ("importance critique",)),
)


def _sections(path: pathlib.Path | None = None) -> list[dict[str, Any]]:
    """Rubriques du jeu A10, telles que le chargeur les met en base (mêmes fonctions, même texte)."""
    from recallpharma.seed.a10 import DEFAULT_PATH
    from recallpharma.seed.spc_texts import spc_sections

    raw = json.loads((path or DEFAULT_PATH).read_text(encoding="utf-8"))
    products = {p["id"]: p for p in raw["products"]}
    substances = {s["id"]: s for s in raw["substances"]}
    out = []
    for a in raw["authorisations"]:
        if not a["expected"]["published"]:
            continue
        for s in spc_sections(a, products[a["product_id"]], substances):
            out.append(
                {
                    "ma_id": a["id"],
                    "jurisdiction": a["jurisdiction"],
                    "product": products[a["product_id"]]["name"],
                    "languages": a["spc"]["languages"],
                    "rubric": s.rubric,
                    "language": s.language,
                    "text": s.text,
                }
            )
    return out


def build() -> dict[str, Any]:
    rng = random.Random(SEED)
    sections = _sections()
    spcs = sorted({(s["ma_id"], s["jurisdiction"], s["product"], tuple(s["languages"])) for s in sections})
    fr_only = [x for x in spcs if x[3] == ("fr",)]
    others = [x for x in spcs if x[3] != ("fr",)]
    cases: list[dict[str, Any]] = []

    def product_case(spc: tuple[str, str, str, tuple[str, ...]], language: str, with_ids: bool) -> None:
        ma_id, jurisdiction, product, _ = spc
        rubric = rng.choice(sorted(ASK_EN if language == "en" else ASK_FR))
        question = rng.choice((ASK_EN if language == "en" else ASK_FR)[rubric]).format(p=product)
        cases.append(
            {
                "id": f"rcp-{len(cases) + 1:03d}",
                "kind": "produit" if with_ids else "produit-nommé",
                "question": question,
                "language": language,
                "jurisdiction": jurisdiction,
                "ma_ids": [ma_id] if with_ids else None,
                "relevant": [f"{ma_id}/{rubric}"],
                "spc_languages": list(spc[3]),
            }
        )

    # Un tiers : anglais sur RCP en français seulement (CT-COP-02 côté recherche).
    for i in range(33):
        product_case(fr_only[i % len(fr_only)], "en", with_ids=i % 4 != 3)
    # Le reste : français sur tous les RCP, anglais sur les RCP bilingues ou anglais.
    for i in range(43):
        product_case(rng.choice(spcs), "fr", with_ids=i % 4 != 3)
    for i in range(16):
        product_case(rng.choice(others), "en", with_ids=i % 4 != 3)
    for jurisdiction in ("PA", "PB"):
        for question, language, rubric, words in REGISTRY:
            # Pays A et Pays B : aucune AMM communautaire n'y vaut (RG-05), les nationales suffisent.
            visible = {s["ma_id"] for s in sections if s["jurisdiction"] == jurisdiction}
            relevant = sorted(
                {
                    f"{s['ma_id']}/{rubric}"
                    for s in sections
                    if s["ma_id"] in visible
                    and s["rubric"] == rubric
                    and s["language"] == "fr"
                    and any(w in s["text"] for w in words)
                }
            )
            if relevant and len(cases) < 100:
                cases.append(
                    {
                        "id": f"rcp-{len(cases) + 1:03d}",
                        "kind": "registre",
                        "question": question,
                        "language": language,
                        "jurisdiction": jurisdiction,
                        "ma_ids": None,
                        "relevant": relevant,
                        "spc_languages": [],
                    }
                )
    return {
        "version": VERSION,
        "description": "Recherche de passages de RCP : 100 questions, rubriques pertinentes (D6)",
        "threshold_recall_at_10": THRESHOLD,
        "cases": cases[:100],
    }


def evaluate(cases: list[dict[str, Any]], full_text: bool) -> dict[str, Any]:
    from recallpharma.api.spc import find_passages
    from recallpharma.db.session import session_factory

    details, mode, model_id = [], None, None
    with session_factory()() as db:
        for c in cases:
            out = find_passages(
                db, c["question"], c["jurisdiction"], c["ma_ids"], 10, embedder=_NoModel() if full_text else None
            )
            mode, model_id = out.mode, out.embedding_model
            got = [f"{p.authorisation_id}/{p.rubric}" for p in out.passages]
            ranked = list(dict.fromkeys(got))
            first = next((i for i, k in enumerate(ranked, start=1) if k in c["relevant"]), None)
            details.append(
                {
                    "id": c["id"],
                    "kind": c["kind"],
                    "language": c["language"],
                    "cross_lingual": c["language"] == "en" and c["spc_languages"] == ["fr"],
                    "recall": recall_at(got, c["relevant"]),
                    # Plus sévère que le seuil D6 : un RCP fictif n'a que 12 rubriques, dix extraits en couvrent
                    # presque toutes. Le rappel à 3 et le premier rang départagent les modes.
                    "recall_at_3": recall_at(ranked, c["relevant"], k=3),
                    "reciprocal_rank": 1 / first if first else 0.0,
                    "top": ranked[:3],
                }
            )
    return {"mode": mode, "embedding_model": model_id, "details": details}


class _NoModel:
    model_id = "aucun"

    def embed(self, texts: list[str]) -> list[list[float]]:
        from recallpharma.retrieval.embeddings import EmbeddingUnavailable

        raise EmbeddingUnavailable("plein texte demandé")


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def summary(report: dict[str, Any]) -> dict[str, dict[str, float]]:
    d = report["details"]
    groups = {
        "tous": d,
        "anglais sur RCP en français": [x for x in d if x["cross_lingual"]],
        "produit connu (ma_ids)": [x for x in d if x["kind"] == "produit"],
        "produit nommé seulement": [x for x in d if x["kind"] == "produit-nommé"],
        "registre": [x for x in d if x["kind"] == "registre"],
    }
    return {
        name: {
            "n": len(rows),
            "recall_at_10": _mean([x["recall"] for x in rows]),
            "recall_at_3": _mean([x["recall_at_3"] for x in rows]),
            "first_rank_ok": _mean([x["reciprocal_rank"] == 1.0 for x in rows]),
            "mrr": _mean([x["reciprocal_rank"] for x in rows]),
        }
        for name, rows in groups.items()
    }


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true", help="régénère le jeu de référence depuis le jeu A10")
    parser.add_argument("--full-text", action="store_true", help="plein texte seul (comparaison)")
    parser.add_argument("--json", type=pathlib.Path)
    args = parser.parse_args()
    if args.build:
        ref = build()
        REFERENCE.write_text(json.dumps(ref, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"{len(ref['cases'])} questions écrites dans {REFERENCE.name}")
        return 0
    ref = json.loads(REFERENCE.read_text(encoding="utf-8"))
    report = evaluate(ref["cases"], args.full_text)
    scores = summary(report)
    print(f"Jeu {ref['version']} · mode {report['mode']} · plongements {report['embedding_model'] or 'aucun'}")
    print(f"  {'':<30} {'n':>4} {'rappel@10':>10} {'rappel@3':>9} {'1er rang':>9} {'MRR':>6}")
    for name, v in scores.items():
        print(
            f"  {name:<30} {v['n']:>4} {v['recall_at_10']:>10.3f} {v['recall_at_3']:>9.3f}"
            f" {v['first_rank_ok']:>9.3f} {v['mrr']:>6.3f}"
        )
    passed = scores["tous"]["recall_at_10"] >= THRESHOLD
    print(f"Seuil {THRESHOLD:.2f} : {'atteint' if passed else 'non atteint'}")
    for x in report["details"]:
        if x["recall_at_3"] < 1:
            print(f"  hors des 3 premiers : {x['id']} {x['kind']} {x['language']} · tête {x['top']}")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        payload = {"reference_version": ref["version"], **report, "summary": scores, "threshold": THRESHOLD}
        args.json.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
