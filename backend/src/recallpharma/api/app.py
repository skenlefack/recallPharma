from __future__ import annotations

from fastapi import FastAPI

from recallpharma.api import curation, problems, registry


def create_app() -> FastAPI:
    app = FastAPI(
        title="RecallPharma API",
        version="0.1.0",
        description="Référentiel du médicament vétérinaire : statut calculé, preuves, délais d'attente, alertes.",
    )
    problems.install(app)
    app.include_router(registry.router)
    app.include_router(curation.router)

    @app.get("/health", tags=["exploitation"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
