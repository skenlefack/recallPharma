"""Recherche hybride des passages de RCP (D4) : plein texte et plus proches voisins, fusionnés par les rangs.

Le filtre sur les versions de RCP admises (juridiction, version publiée) est appliqué dans les deux recherches,
avant tout classement : un passage d'une autre juridiction ne peut pas remonter, même très proche.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Collection, Sequence
from dataclasses import dataclass

from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from recallpharma.db import models as m
from recallpharma.domain.passages import fuse
from recallpharma.retrieval.embeddings import Embedder, EmbeddingUnavailable, get_embedder

CANDIDATES = 50  # profondeur de chaque classement avant fusion
HYBRID, FULL_TEXT = "hybride", "plein texte"
# Mots vides qui survivent aux dictionnaires français et anglais après suppression des accents.
_STOP = {"le", "la", "les", "de", "du", "des", "quel", "chez", "pour", "est", "sont", "what", "which", "are", "doe"}
_LEXEME = re.compile(r"'([^']+)'")


@dataclass(frozen=True, slots=True)
class Hit:
    passage_id: int
    score: float
    full_text_rank: int | None
    vector_rank: int | None


def _tsquery(db: Session, query: str) -> str | None:
    """Disjonction des racines françaises et anglaises de la question : le classement fait le tri, pas le filtre."""
    row = db.execute(
        text(
            "SELECT plainto_tsquery('french', reg.f_unaccent(:q))::text, "
            "plainto_tsquery('english', reg.f_unaccent(:q))::text"
        ),
        {"q": query},
    ).one()
    lexemes = sorted({lx for part in row for lx in _LEXEME.findall(part or "") if len(lx) > 2 and lx not in _STOP})
    return " | ".join(f"'{lx}'" for lx in lexemes) or None


def _full_text(db: Session, query: str, versions: Collection[int]) -> list[int]:
    q = _tsquery(db, query)
    if q is None:
        return []
    rows = db.execute(
        text(
            "SELECT p.id FROM reg.spc_passage p JOIN reg.spc_section s ON s.id = p.section_id, "
            "CAST(:q AS tsquery) AS q WHERE s.spc_version_id = ANY(:v) AND p.tsv @@ q "
            "ORDER BY ts_rank_cd(p.tsv, q) DESC, p.id LIMIT :n"
        ),
        {"q": q, "v": list(versions), "n": CANDIDATES},
    )
    return [r[0] for r in rows]


def _nearest(db: Session, vector: list[float], model_id: str, versions: Collection[int]) -> list[int]:
    # Parcours itératif de l'index HNSW : le filtre de juridiction ne vide pas le voisinage (pgvector ≥ 0.8).
    db.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
    distance = m.SpcPassage.embedding.cosine_distance(vector)
    rows = db.execute(
        select(m.SpcPassage.id)
        .join(m.SpcSection, m.SpcSection.id == m.SpcPassage.section_id)
        .where(m.SpcSection.spc_version_id.in_(list(versions)), m.SpcPassage.embedding_model == model_id)
        .order_by(distance, m.SpcPassage.id)
        .limit(CANDIDATES)
    )
    return [r[0] for r in rows]


def search_passages(
    db: Session, query: str, versions: Collection[int], limit: int = 10, embedder: Embedder | None = None
) -> tuple[list[Hit], str, str | None]:
    """Passages classés, mode effectif (« hybride » ou « plein texte ») et modèle de plongements employé."""
    if not versions:
        return [], FULL_TEXT, None
    embedder = embedder or get_embedder()
    full = _full_text(db, query, versions)
    near: list[int] = []
    mode, model_id = FULL_TEXT, None
    if embedder is not None:
        try:
            (vector,) = embedder.embed([query])
        except EmbeddingUnavailable:
            vector = None  # modèle injoignable : le plein texte répond seul, et la réponse le dit
        if vector is not None:
            near = _nearest(db, vector, embedder.model_id, versions)
            mode, model_id = HYBRID, embedder.model_id
    ranks_full = {pid: i for i, pid in enumerate(full, start=1)}
    ranks_near = {pid: i for i, pid in enumerate(near, start=1)}
    hits = [
        Hit(pid, round(score, 5), ranks_full.get(pid), ranks_near.get(pid))
        for pid, score in fuse([full, near], limit=limit)
    ]
    return hits, mode, model_id


def index_passages(db: Session, embedder: Embedder, batch: int = 32, reindex: bool = False) -> int:
    """Calcule les plongements manquants, ou d'un autre modèle : un changement de modèle impose la réindexation."""
    if reindex:
        db.execute(update(m.SpcPassage).values(embedding=None, embedding_model=None))
    todo: Sequence[m.SpcPassage] = db.scalars(
        select(m.SpcPassage)
        .where((m.SpcPassage.embedding_model.is_(None)) | (m.SpcPassage.embedding_model != embedder.model_id))
        .order_by(m.SpcPassage.id)
    ).all()
    for start in range(0, len(todo), batch):
        chunk = todo[start : start + batch]
        for passage, vector in zip(chunk, embedder.embed([f"{p.heading}. {p.text}" for p in chunk]), strict=True):
            passage.embedding, passage.embedding_model = vector, embedder.model_id
        db.flush()
    return len(todo)


def main() -> int:
    """`python -m recallpharma.retrieval.search [--reindex]` : indexe les passages avec le modèle configuré."""
    from recallpharma.db.session import session_factory

    embedder = get_embedder(timeout_s=600)
    if embedder is None:
        print("Aucun modèle de plongements configuré (RECALLPHARMA_EMBED_BASE_URL).")
        return 1
    with session_factory()() as db, db.begin():
        n = index_passages(db, embedder, reindex="--reindex" in sys.argv)
    print(f"{n} passages indexés avec {embedder.model_id}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
