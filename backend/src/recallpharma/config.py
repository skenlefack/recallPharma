from __future__ import annotations

from datetime import date
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RECALLPHARMA_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://recallpharma:recallpharma@localhost:5434/recallpharma"
    # Date de consultation imposée (démonstration sur le jeu A10, daté du 2027-09-07) ; vide = aujourd'hui.
    reference_date: date | None = None
    # Dépôt local des documents sources ; stockage objet S3 avec verrouillage en production (ADR-13).
    storage_dir: str = "var/documents"
    # Authentification : jetons OIDC émis par Keycloak. « dev » (en-tête X-RecallPharma-User) est réservé aux tests.
    auth_mode: Literal["oidc", "dev"] = "oidc"
    oidc_issuer: str = "http://localhost:8280/realms/recallpharma"
    oidc_audience: str = "recallpharma-api"
    # Vide = <issuer>/protocol/openid-connect/certs.
    oidc_jwks_url: str | None = None

    # Copilot (D6). Jeton délégué : émis par l'API pour la passerelle, accepté sur les seuls outils de lecture (ADR-08).
    copilot_token_secret: str = "dev-only-copilot-delegation-secret"
    copilot_token_audience: str = "api-copilot-lecture"
    copilot_quota_hour: int = 30
    copilot_quota_day: int = 200
    copilot_max_turns: int = 20
    gateway_url: str = "http://127.0.0.1:8001"  # passerelle d'IA, vue de l'API
    api_url: str = "http://127.0.0.1:8000"  # API, vue de la passerelle (outils)
    # Modèle open source servi par une interface compatible OpenAI : vLLM en production, Ollama en développement.
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "qwen2.5:7b-instruct"
    llm_api_key: str | None = None
    llm_timeout_s: float = 120.0
    # Plongements des passages de RCP (D4) : serveur compatible OpenAI (/embeddings). « hash: » = encodeur lexical
    # déterministe (tests, poste sans modèle) ; vide = plein texte seul.
    embed_base_url: str = "http://localhost:11434/v1"
    embed_model: str = "bge-m3"
    embed_api_key: str | None = None
    embed_timeout_s: float = 5.0  # délai d'un outil (D5)


@lru_cache
def get_settings() -> Settings:
    return Settings()
