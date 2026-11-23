"""Erreurs au format RFC 9457 (application/problem+json), sans détail interne."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM = "application/problem+json"


class Problem(Exception):
    def __init__(self, status: int, code: str, title: str, detail: str | None = None, **extra: Any) -> None:
        self.status, self.code, self.title, self.detail, self.extra = status, code, title, detail, extra


def _response(status: int, code: str, title: str, detail: str | None, instance: str, **extra: Any) -> JSONResponse:
    body = {
        "type": f"https://recallpharma.example/problems/{code}",
        "title": title,
        "status": status,
        "instance": instance,
        **({"detail": detail} if detail else {}),
        **extra,
    }
    return JSONResponse(body, status_code=status, media_type=PROBLEM)


def install(app: FastAPI) -> None:
    @app.exception_handler(Problem)
    async def _problem(request: Request, exc: Problem) -> JSONResponse:
        return _response(exc.status, exc.code, exc.title, exc.detail, request.url.path, **exc.extra)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _response(exc.status_code, "http", str(exc.detail), None, request.url.path)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
        return _response(422, "validation", "Requête invalide", None, request.url.path, errors=errors)
