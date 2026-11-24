"""Recettes d'entraînement (JSON versionnés dans recettes/) et choix reproductible des exemples."""

from __future__ import annotations

import hashlib
import json
import pathlib
import platform
import random
from collections import defaultdict
from typing import Any

RECIPES = pathlib.Path(__file__).with_name("recettes")


def load_recipe(name_or_path: str) -> dict[str, Any]:
    path = pathlib.Path(name_or_path)
    if not path.exists():
        path = RECIPES / f"{name_or_path}.json"
    recipe: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    recipe["_path"] = str(path)
    recipe["_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return recipe


def read_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def stratified(rows: list[dict[str, Any]], limit: int | None, seed: int) -> list[dict[str, Any]]:
    """Sous-échantillon qui garde la proportion de chaque (intention, étape) ; tout le jeu si limit est nul."""
    if not limit or limit >= len(rows):
        return list(rows)
    rng = random.Random(seed)
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[(r["intent"], r["step"])].append(r)
    picked: list[dict[str, Any]] = []
    for key in sorted(groups):
        group = groups[key]
        rng.shuffle(group)
        share = max(1, round(limit * len(group) / len(rows)))
        picked += group[:share]
    rng.shuffle(picked)
    return picked[:limit]


def provenance(recipe: dict[str, Any], data_dir: pathlib.Path) -> dict[str, Any]:
    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    return {
        "recipe": recipe["name"],
        "recipe_sha256": recipe["_sha256"],
        "base_model": recipe["base_model_id"],
        "licence": recipe["licence"],
        "dataset_version": manifest["dataset_version"],
        "dataset_sha256": manifest["sha256"],
        "prompt_version": manifest["prompt_version"],
        "tools_version": manifest["tools_version"],
        "machine": f"{platform.system()} {platform.machine()} · Python {platform.python_version()}",
    }
