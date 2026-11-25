#!/bin/sh
# Prépare la base : schéma à jour, jeu fictif A10 si la base est vide, plongements des passages de RCP manquants.
set -e
alembic upgrade head
python - <<'PY'
from sqlalchemy import func, select

from recallpharma.db import models as m
from recallpharma.db.session import session_factory
from recallpharma.seed.load_db import load_a10

with session_factory()() as session, session.begin():
    if session.scalar(select(func.count()).select_from(m.Authorisation)):
        print("Base déjà chargée : jeu A10 conservé.")
    else:
        print(f"{load_a10(session)} AMM fictives chargées.")
PY
python -m recallpharma.retrieval.search || echo "Plongements indisponibles : la recherche dans les RCP restera en plein texte."
