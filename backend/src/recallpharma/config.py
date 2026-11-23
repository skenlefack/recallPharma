from __future__ import annotations

from datetime import date
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RECALLPHARMA_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://recallpharma:recallpharma@localhost:5434/recallpharma"
    # Date de consultation imposée (démonstration sur le jeu A10, daté du 2027-09-07) ; vide = aujourd'hui.
    reference_date: date | None = None
    # Dépôt local des documents sources ; stockage objet S3 avec verrouillage en production (ADR-13).
    storage_dir: str = "var/documents"


@lru_cache
def get_settings() -> Settings:
    return Settings()
