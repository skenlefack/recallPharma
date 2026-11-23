"""Copilot côté API (M5) : conversations, quotas, jeton délégué, relais du flux de la passerelle et journal (D5, D6).

L'API ne parle jamais au modèle : elle transmet la question à la passerelle d'IA avec un jeton délégué en lecture,
relaie ses événements au client et enregistre l'échange (question masquée, outils, contrôle, réponse).
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Annotated, Any, Literal

import httpx
from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from recallpharma.api import registry
from recallpharma.api.auth import Identity, IdentityDep, mint_delegated
from recallpharma.api.problems import Problem
from recallpharma.config import get_settings
from recallpharma.curation import service
from recallpharma.db import models as m
from recallpharma.db.audit import record
from recallpharma.db.session import session_factory
from recallpharma.domain import copilot as cp
from recallpharma.domain import curation as c

router = APIRouter(prefix="/v1/copilot", tags=["copilot"])

#: Utiliser le Copilot (D3) : professionnel vérifié, agent d'autorité, validateur, responsable réglementaire,
#: évaluateur de pharmacovigilance.
COPILOT_ROLES = frozenset(
    {
        "Professionnel vérifié",
        "Agent d'autorité",
        c.Role.VALIDATOR.value,
        c.Role.REGULATORY_LEAD.value,
        "Évaluateur de pharmacovigilance",
    }
)
JOURNAL_ROLES = frozenset({"Auditeur"})

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<!\w)\+?\d[\d .-]{7,}\d(?!\w)")


def mask(text: str) -> str:
    """Question enregistrée après masquage des adresses électroniques et des numéros de téléphone (D6)."""
    return _PHONE.sub("[téléphone]", _EMAIL.sub("[courriel]", text))


@lru_cache
def get_gateway() -> httpx.Client:
    s = get_settings()
    return httpx.Client(base_url=s.gateway_url, timeout=httpx.Timeout(s.llm_timeout_s * 3, connect=3.0))


Gateway = Annotated[httpx.Client, Depends(get_gateway)]


def _session() -> Iterator[Session]:
    with session_factory()() as s:
        yield s


DB = Annotated[Session, Depends(_session)]


def _actor(db: Session, identity: Identity) -> c.Actor:
    try:
        if identity.account_id is not None:
            return service.actor_for(db, identity.account_id)
        assert identity.login is not None
        actor = service.actor_for_login(db, identity.login, identity.roles)
        db.commit()  # rôles recopiés et audités, même pour une simple lecture
        return actor
    except c.WorkflowError as e:
        raise Problem(401, e.code, e.message) from e


def _user(db: Session, identity: Identity) -> c.Actor:
    actor = _actor(db, identity)
    if not actor.roles & COPILOT_ROLES:
        raise Problem(
            403, "forbidden", "Le Copilot est réservé aux professionnels vérifiés et aux équipes réglementaires"
        )
    return actor


def _own(db: Session, actor: c.Actor, conversation_id: uuid.UUID) -> m.CopilotConversation:
    conv = db.get(m.CopilotConversation, conversation_id)
    if conv is None or conv.account_id != actor.id:
        raise Problem(404, "not_found", "Conversation inconnue")
    return conv


# --- Contrat ------------------------------------------------------------------------------------


class ConversationIn(BaseModel):
    jurisdiction: str


class MessageIn(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class FeedbackIn(BaseModel):
    rating: Literal["utile", "erreur signalée", "autre"]
    comment: str | None = Field(None, max_length=2000)


class MessageOut(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    payload: dict[str, Any] | None
    known_at: datetime


class ConversationOut(BaseModel):
    id: uuid.UUID
    jurisdiction: str
    jurisdiction_name: str
    started_at: datetime
    turns: int
    messages: list[MessageOut] = []


class ToolCallOut(BaseModel):
    tool: str
    arguments: dict[str, Any]
    result: dict[str, Any] | None
    duration_ms: int | None


class JournalEntry(MessageOut):
    jurisdiction: str | None
    model_id: str | None
    prompt_version: str | None
    tools_version: str | None
    rules_version: str | None
    tokens_in: int | None
    tokens_out: int | None
    duration_ms: int | None
    injection_suspected: bool
    tool_calls: list[ToolCallOut]
    check: dict[str, Any] | None


def _conversation_out(db: Session, conv: m.CopilotConversation, with_messages: bool = False) -> ConversationOut:
    j = db.get(m.Jurisdiction, conv.jurisdiction_code)
    return ConversationOut(
        id=conv.id,
        jurisdiction=conv.jurisdiction_code,
        jurisdiction_name=j.name if j else conv.jurisdiction_code,
        started_at=conv.started_at,
        turns=sum(1 for x in conv.messages if x.role == "utilisateur"),
        messages=[
            MessageOut(id=x.id, role=x.role, content=x.content, payload=x.payload, known_at=x.known_at)
            for x in conv.messages
        ]
        if with_messages
        else [],
    )


# --- Conversations -------------------------------------------------------------------------------


@router.post("/conversations", response_model=ConversationOut, status_code=201)
def create_conversation(db: DB, identity: IdentityDep, body: ConversationIn) -> ConversationOut:
    actor = _user(db, identity)
    if db.get(m.Jurisdiction, body.jurisdiction) is None:
        raise Problem(422, "jurisdiction_not_covered", f"Juridiction non couverte : {body.jurisdiction}")
    conv = m.CopilotConversation(account_id=actor.id, jurisdiction_code=body.jurisdiction)
    db.add(conv)
    db.commit()
    return _conversation_out(db, conv)


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(db: DB, identity: IdentityDep) -> list[ConversationOut]:
    actor = _user(db, identity)
    rows = db.scalars(
        select(m.CopilotConversation)
        .where(m.CopilotConversation.account_id == actor.id)
        .order_by(m.CopilotConversation.started_at.desc())
        .limit(50)
    )
    return [_conversation_out(db, x) for x in rows]


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
def get_conversation(db: DB, identity: IdentityDep, conversation_id: uuid.UUID) -> ConversationOut:
    return _conversation_out(db, _own(db, _user(db, identity), conversation_id), with_messages=True)


@router.put("/conversations/{conversation_id}", response_model=ConversationOut)
def change_jurisdiction(
    db: DB, identity: IdentityDep, conversation_id: uuid.UUID, body: ConversationIn
) -> ConversationOut:
    conv = _own(db, _user(db, identity), conversation_id)
    if db.get(m.Jurisdiction, body.jurisdiction) is None:
        raise Problem(422, "jurisdiction_not_covered", f"Juridiction non couverte : {body.jurisdiction}")
    conv.jurisdiction_code = body.jurisdiction
    db.commit()
    return _conversation_out(db, conv)


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(db: DB, identity: IdentityDep, conversation_id: uuid.UUID) -> Response:
    """Effacement par l'utilisateur (D7) : messages, outils, contrôles et jeux de résultats disparaissent avec elle."""
    db.delete(_own(db, _user(db, identity), conversation_id))
    db.commit()
    return Response(status_code=204)


@router.get("/conversations/{conversation_id}/journal", response_model=list[JournalEntry])
def journal(db: DB, identity: IdentityDep, conversation_id: uuid.UUID) -> list[JournalEntry]:
    """Reconstitution d'un échange (CT-COP-06) : question, outils, résultats, versions, contrôle et réponse."""
    actor = _actor(db, identity)
    conv = db.get(m.CopilotConversation, conversation_id)
    if conv is None or (conv.account_id != actor.id and not actor.roles & JOURNAL_ROLES):
        raise Problem(404, "not_found", "Conversation inconnue")
    return [
        JournalEntry(
            id=x.id,
            role=x.role,
            content=x.content,
            payload=x.payload,
            known_at=x.known_at,
            jurisdiction=x.jurisdiction_code,
            model_id=x.model_id,
            prompt_version=x.prompt_version,
            tools_version=x.tools_version,
            rules_version=x.rules_version,
            tokens_in=x.tokens_in,
            tokens_out=x.tokens_out,
            duration_ms=x.duration_ms,
            injection_suspected=x.injection_suspected,
            tool_calls=[
                ToolCallOut(tool=t.tool, arguments=t.arguments, result=t.result, duration_ms=t.duration_ms)
                for t in x.tool_calls
            ],
            check={"passed": x.check.passed, "attempts": x.check.attempts, **(x.check.details or {})}
            if x.check
            else None,
        )
        for x in conv.messages
    ]


@router.post("/messages/{message_id}/feedback", status_code=201)
def feedback(db: DB, identity: IdentityDep, message_id: uuid.UUID, body: FeedbackIn) -> dict[str, str]:
    """Signalement d'une réponse (CT-COP-07) : ticket de qualité dans le journal d'audit, accusé de réception."""
    actor = _user(db, identity)
    msg = db.get(m.CopilotMessage, message_id)
    if msg is None or msg.role != "copilot" or _own(db, actor, msg.conversation_id) is None:
        raise Problem(404, "not_found", "Réponse inconnue")
    if db.get(m.CopilotFeedback, message_id) is not None:
        raise Problem(409, "already_given", "Un retour a déjà été donné sur cette réponse")
    db.add(m.CopilotFeedback(message_id=message_id, rating=body.rating, comment=body.comment))
    ticket = None
    if body.rating == "erreur signalée":
        event = record(
            db,
            actor=actor.id,
            action="copilot.error_reported",
            object_type="copilot_message",
            object_id=str(message_id),
            after={"conversation_id": str(msg.conversation_id), "comment": body.comment},
            reason="ticket de qualité",
        )
        ticket = f"QUAL-{event.seq}"
    db.commit()
    return {"status": "reçu", **({"ticket": ticket} if ticket else {})}


# --- Question : relais du flux de la passerelle ----------------------------------------------------


def _quota(db: Session, actor: c.Actor) -> None:
    s = get_settings()
    now = datetime.now(UTC)

    def since(delta: timedelta) -> int:
        return int(
            db.scalar(
                select(func.count())
                .select_from(m.CopilotMessage)
                .join(m.CopilotConversation)
                .where(
                    m.CopilotConversation.account_id == actor.id,
                    m.CopilotMessage.role == "utilisateur",
                    m.CopilotMessage.known_at > now - delta,
                )
            )
            or 0
        )

    if since(timedelta(hours=1)) >= s.copilot_quota_hour or since(timedelta(days=1)) >= s.copilot_quota_day:
        raise Problem(429, "quota_exceeded", "Quota de questions atteint : réessayer plus tard")


def _event(name: str, data: dict[str, Any]) -> str:
    return f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def _parse(lines: Iterator[str]) -> Iterator[tuple[str, dict[str, Any]]]:
    name, data = "message", ""
    for line in lines:
        if line.startswith("event:"):
            name = line[6:].strip()
        elif line.startswith("data:"):
            data += line[5:].strip()
        elif not line.strip() and data:
            yield name, json.loads(data)
            name, data = "message", ""


@router.post("/conversations/{conversation_id}/messages")
def ask(
    db: DB, identity: IdentityDep, gateway: Gateway, conversation_id: uuid.UUID, body: MessageIn
) -> StreamingResponse:
    """Flux text/event-stream : `status`, `records` (bandeaux et tableau), `answer` (après contrôle), `done`."""
    actor = _user(db, identity)
    conv = _own(db, actor, conversation_id)
    if sum(1 for x in conv.messages if x.role == "utilisateur") >= get_settings().copilot_max_turns:
        raise Problem(409, "conversation_full", "Conversation de 20 tours : en ouvrir une nouvelle")
    _quota(db, actor)

    history: list[dict[str, str]] = []
    pending: str | None = None
    for x in conv.messages:
        if x.role == "utilisateur":
            pending = x.content
        elif pending is not None:
            history.append({"question": pending, "answer": x.content})
            pending = None
    latest = db.scalars(
        select(m.ResultSet)
        .where(m.ResultSet.conversation_id == conv.id, m.ResultSet.expires_at > datetime.now(UTC))
        .order_by(m.ResultSet.created_at.desc())
        .limit(1)
    ).first()
    jurisdiction = db.get(m.Jurisdiction, conv.jurisdiction_code)
    assert jurisdiction is not None
    db.add(
        m.CopilotMessage(
            conversation_id=conv.id,
            role="utilisateur",
            content=mask(body.content),
            jurisdiction_code=conv.jurisdiction_code,
            injection_suspected=cp.looks_like_injection(body.content),
        )
    )
    db.commit()
    request = {
        "question": body.content,
        "jurisdiction": conv.jurisdiction_code,
        "jurisdiction_name": jurisdiction.name,
        "as_of": registry.resolve_as_of(None).isoformat(),
        "token": mint_delegated(actor.id, str(conv.id)),
        "result_set_id": str(latest.id) if latest else None,
        "result_set_query": latest.query if latest else None,
        "history": history[-3:],
    }
    return StreamingResponse(_relay(gateway, conv.id, request), media_type="text/event-stream")


def _relay(gateway: httpx.Client, conversation_id: uuid.UUID, request: dict[str, Any]) -> Iterator[str]:
    payload: dict[str, Any] = {}
    trace: dict[str, Any] | None = None
    try:
        with gateway.stream("POST", "/v1/answer", json=request) as res:
            if res.status_code != 200:
                raise httpx.HTTPStatusError("passerelle en erreur", request=res.request, response=res)
            for name, data in _parse(res.iter_lines()):
                if name == "trace":
                    trace = data
                    continue
                if name in ("records", "answer", "error"):
                    payload[name] = data
                yield _event(name, data)
    except (httpx.HTTPError, json.JSONDecodeError):
        payload["error"] = {"code": "copilot_unavailable", "message": cp.UNAVAILABLE}
        yield _event("error", payload["error"])
    message_id = _store(conversation_id, request["jurisdiction"], payload, trace)
    yield _event("done", {"message_id": str(message_id)})


def _store(
    conversation_id: uuid.UUID, jurisdiction: str, payload: dict[str, Any], trace: dict[str, Any] | None
) -> uuid.UUID:
    answer = payload.get("answer") or payload.get("error") or {}
    t = trace or {}
    with session_factory()() as db, db.begin():
        msg = m.CopilotMessage(
            conversation_id=conversation_id,
            role="copilot",
            content=str(answer.get("text") or answer.get("message") or ""),
            payload=payload,
            jurisdiction_code=jurisdiction,
            model_id=t.get("model_id"),
            prompt_version=t.get("prompt_version"),
            tools_version=t.get("tools_version"),
            rules_version=t.get("rules_version"),
            tokens_in=t.get("tokens_in"),
            tokens_out=t.get("tokens_out"),
            duration_ms=t.get("duration_ms"),
            injection_suspected=bool(t.get("injection_suspected")),
        )
        db.add(msg)
        db.flush()
        for i, call in enumerate(t.get("tool_calls", [])):
            db.add(
                m.CopilotToolCall(
                    message_id=msg.id,
                    position=i,
                    tool=call["tool"],
                    arguments=call.get("arguments") or {},
                    result=call.get("result"),
                    duration_ms=call.get("duration_ms"),
                )
            )
        check = t.get("check")
        if check is not None or t.get("abstention"):
            check = check or {}
            db.add(
                m.CopilotCheck(
                    message_id=msg.id,
                    passed=bool(check.get("passed", False)),
                    attempts=int(check.get("attempts", 0)),
                    details={
                        "problems": check.get("problems", []),
                        "refs": check.get("refs", []),
                        "abstention": t.get("abstention"),
                    },
                )
            )
        return msg.id
