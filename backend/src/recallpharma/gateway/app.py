"""Service passerelle-ia : reçoit une question de l'API, rend un flux d'événements (text/event-stream).

Démarrage : uvicorn recallpharma.gateway.app:app --port 8001
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated, Any

import httpx
from fastapi import Depends, FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from recallpharma.config import get_settings
from recallpharma.gateway.llm import ChatModel, OpenAICompatibleModel
from recallpharma.gateway.orchestrator import Orchestrator, Question
from recallpharma.gateway.tools import ToolRunner


class HistoryItem(BaseModel):
    question: str
    answer: str


class AnswerIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    jurisdiction: str
    jurisdiction_name: str
    as_of: str
    token: str  # jeton délégué en lecture (ADR-08), jamais le jeton de l'utilisateur
    result_set_id: str | None = None
    result_set_query: dict[str, Any] | None = None
    history: list[HistoryItem] = []


@lru_cache
def get_model() -> ChatModel:
    s = get_settings()
    return OpenAICompatibleModel(s.llm_base_url, s.llm_model, api_key=s.llm_api_key, timeout=s.llm_timeout_s)


@lru_cache
def get_api() -> httpx.Client:
    return httpx.Client(base_url=get_settings().api_url, timeout=5.0)


def sse(events: Iterator[tuple[str, dict[str, Any]]]) -> Iterator[str]:
    for name, data in events:
        yield f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def create_app() -> FastAPI:
    app = FastAPI(title="RecallPharma — passerelle d'IA", version="0.1.0")

    @app.post("/v1/answer")
    def answer(
        body: AnswerIn,
        model: Annotated[ChatModel, Depends(get_model)],
        api: Annotated[httpx.Client, Depends(get_api)],
    ) -> StreamingResponse:
        runner = ToolRunner(api, body.token, body.jurisdiction, body.result_set_id)
        question = Question(
            text=body.question,
            jurisdiction=body.jurisdiction,
            jurisdiction_name=body.jurisdiction_name,
            as_of=body.as_of,
            result_set_id=body.result_set_id,
            result_set_query=body.result_set_query,
            history=[h.model_dump() for h in body.history],
        )
        return StreamingResponse(sse(Orchestrator(model, runner).run(question)), media_type="text/event-stream")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "model": get_settings().llm_model}

    return app


app = create_app()
