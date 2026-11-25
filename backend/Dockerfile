# Image unique de l'API, de la passerelle d'IA et de l'initialisation de la base (schéma, jeu A10, index des RCP).
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv PATH="/opt/venv/bin:$PATH"
WORKDIR /app

# Dépendances d'exécution seules (ni outils de développement ni bibliothèques d'entraînement).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY alembic.ini ./
COPY migrations ./migrations
COPY src ./src
COPY docker/init.sh /usr/local/bin/recallpharma-init
RUN uv sync --frozen --no-dev && chmod +x /usr/local/bin/recallpharma-init \
    && useradd --create-home --uid 10001 app && mkdir -p var/documents && chown -R app var
USER app

EXPOSE 8000
CMD ["uvicorn", "recallpharma.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
