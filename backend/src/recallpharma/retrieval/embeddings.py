"""Modèle de plongements : un modèle multilingue ouvert, servi à part par une interface compatible OpenAI (D4).

Production : un serveur d'inférence (vLLM, TEI) ; développement : Ollama avec bge-m3 (MIT, 1024 dimensions). L'API ne
charge aucune bibliothèque d'apprentissage : elle envoie le texte et reçoit le vecteur. Sans modèle joignable, la
recherche se replie sur le plein texte et le dit. L'encodeur par hachage, lexical et déterministe, sert aux tests et
au poste sans modèle ; il ne rapproche pas deux langues.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from functools import lru_cache
from typing import Protocol

import httpx

from recallpharma.config import get_settings
from recallpharma.db.models import EMBEDDING_DIMS

HASH_MODEL = "hachage-lexical-v1"


class EmbeddingUnavailable(Exception):
    pass


class Embedder(Protocol):
    model_id: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


def _unit(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vector)) or 1.0
    return [x / norm for x in vector]


class HttpEmbedder:
    def __init__(self, base_url: str, model: str, timeout_s: float, api_key: str | None = None) -> None:
        self.model_id = model
        headers = {"authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout_s, headers=headers)

    def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            res = self._client.post("/embeddings", json={"model": self.model_id, "input": texts})
            res.raise_for_status()
            data = sorted(res.json()["data"], key=lambda d: d["index"])
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise EmbeddingUnavailable(str(exc)) from exc
        vectors = [_unit([float(x) for x in d["embedding"]]) for d in data]
        if len(vectors) != len(texts) or any(len(v) != EMBEDDING_DIMS for v in vectors):
            raise EmbeddingUnavailable(f"réponse inattendue du modèle {self.model_id}")
        return vectors


class HashEmbedder:
    """Sac de racines (6 premières lettres, sans accents) projeté par hachage : un voisin lexical, rien de plus."""

    model_id = HASH_MODEL

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            plain = "".join(c for c in unicodedata.normalize("NFKD", text.casefold()) if not unicodedata.combining(c))
            vector = [0.0] * EMBEDDING_DIMS
            for word in re.findall(r"[a-z]{3,}", plain):
                digest = hashlib.blake2b(word[:6].encode(), digest_size=8).digest()
                index = int.from_bytes(digest[:4], "big") % EMBEDDING_DIMS
                vector[index] += 1.0 if digest[4] % 2 else -1.0
            out.append(_unit(vector))
        return out


@lru_cache
def get_embedder(timeout_s: float | None = None) -> Embedder | None:
    """« hash: » : encodeur lexical ; vide : aucun (plein texte seul) ; sinon l'URL du serveur de plongements.
    Délai par défaut : celui d'un outil (5 s) ; l'indexation par lots en prend un plus long."""
    s = get_settings()
    if not s.embed_base_url:
        return None
    if s.embed_base_url.startswith("hash:"):
        return HashEmbedder()
    return HttpEmbedder(s.embed_base_url, s.embed_model, timeout_s or s.embed_timeout_s, s.embed_api_key)
