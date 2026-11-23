"""Base de test : une base PostgreSQL neuve par module, migrée puis chargée avec le jeu A10."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from recallpharma.config import get_settings

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


@pytest.fixture(scope="module")
def client(tmp_path_factory: pytest.TempPathFactory) -> Iterator[TestClient]:
    base = make_url(get_settings().database_url)
    test_url = base.set(database="recallpharma_test")
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as c:
            c.execute(text("DROP DATABASE IF EXISTS recallpharma_test WITH (FORCE)"))
            c.execute(text("CREATE DATABASE recallpharma_test"))
    except Exception as exc:  # pragma: no cover - pas de serveur local
        pytest.skip(f"PostgreSQL indisponible : {exc}")

    os.environ["RECALLPHARMA_DATABASE_URL"] = test_url.render_as_string(hide_password=False)
    os.environ["RECALLPHARMA_STORAGE_DIR"] = str(tmp_path_factory.mktemp("documents"))
    os.environ["RECALLPHARMA_REFERENCE_DATE"] = "2027-09-07"
    os.environ.setdefault("RECALLPHARMA_AUTH_MODE", "dev")
    get_settings.cache_clear()
    from recallpharma.db.session import get_engine

    get_engine.cache_clear()
    cfg = Config(os.path.join(ROOT, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(ROOT, "migrations"))
    command.upgrade(cfg, "head")

    from recallpharma.db.session import session_factory
    from recallpharma.seed.load_db import load_a10

    with session_factory()() as session, session.begin():
        load_a10(session)

    from recallpharma.api.app import create_app

    with TestClient(create_app()) as c:
        yield c
    get_engine().dispose()
    get_engine.cache_clear()
    for key in (
        "RECALLPHARMA_DATABASE_URL",
        "RECALLPHARMA_STORAGE_DIR",
        "RECALLPHARMA_REFERENCE_DATE",
        "RECALLPHARMA_AUTH_MODE",
    ):
        os.environ.pop(key, None)
    get_settings.cache_clear()
    admin.dispose()
