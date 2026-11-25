"""Administration : tableau de bord, comptes et rôles, alertes, AMM, signalements du Copilot, journal d'audit.

Accès : administrateurs fonctionnel et technique, auditeur (lecture seule) ; l'évaluateur de pharmacovigilance gère
les alertes. Chaque écriture est tracée dans le journal chaîné (RG-33).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from recallpharma.admin.directory import Directory, DirectoryError, get_directory, temporary_password
from recallpharma.api.auth import ROLE_SLUGS
from recallpharma.api.curation import DB, ActorDep, today
from recallpharma.api.problems import Problem
from recallpharma.api.registry import _assess
from recallpharma.db import models as m
from recallpharma.db.audit import record, verify_chain
from recallpharma.domain import curation as c

router = APIRouter(prefix="/v1/admin", tags=["administration"])

FUNCTIONAL = "Administrateur fonctionnel"
TECHNICAL = "Administrateur technique"
AUDITOR = "Auditeur"
PHARMACOVIGILANCE = "Évaluateur de pharmacovigilance"

READERS = {FUNCTIONAL, TECHNICAL, AUDITOR, PHARMACOVIGILANCE}
ACCOUNT_MANAGERS = {FUNCTIONAL, TECHNICAL}
ALERT_MANAGERS = {FUNCTIONAL, PHARMACOVIGILANCE}

DirectoryDep = Annotated[Directory, Depends(get_directory)]


def _require(actor: c.Actor, allowed: set[str]) -> None:
    if not actor.roles & allowed:
        raise Problem(403, "forbidden", "Rôle insuffisant pour cette action d'administration")


# --- Tableau de bord ---------------------------------------------------------------------------------


class Overview(BaseModel):
    authorisations: dict[str, int]  # par état de publication
    statuses: dict[str, int]  # AMM publiées, par statut réglementaire à la date de référence
    by_jurisdiction: dict[str, int]  # AMM publiées par juridiction
    proposals: dict[str, int]  # propositions en cours, par état
    alerts_open: dict[str, int]  # alertes non closes, par niveau
    alerts_closed: int
    documents: int
    accounts: dict[str, int]  # comptes actifs par rôle
    accounts_inactive: int
    copilot: dict[str, int]
    audit_last_7_days: int
    audit_chain_intact: bool
    as_of: date
    permissions: list[str]


def _counts(rows: Any) -> dict[str, int]:
    return {str(k): int(v) for k, v in rows}


@router.get("/overview", response_model=Overview)
def overview(db: DB, actor: ActorDep) -> Overview:
    _require(actor, READERS)
    day = today()
    published = list(db.scalars(select(m.Authorisation).where(m.Authorisation.publication_state == "publiée")))
    statuses: dict[str, int] = {}
    for row in published:
        status = _assess(row, day).status
        statuses[status] = statuses.get(status, 0) + 1
    accounts: dict[str, int] = {}
    for a in db.scalars(select(m.Account).where(m.Account.active)):
        for r in a.roles:
            accounts[r] = accounts.get(r, 0) + 1
    since = datetime.now(UTC) - timedelta(days=30)
    feedback = _counts(db.execute(select(m.CopilotFeedback.rating, func.count()).group_by(m.CopilotFeedback.rating)))
    permissions = []
    if actor.roles & ACCOUNT_MANAGERS:
        permissions.append("comptes")
    if actor.roles & ALERT_MANAGERS:
        permissions.append("alertes")
    return Overview(
        authorisations=_counts(
            db.execute(
                select(m.Authorisation.publication_state, func.count()).group_by(m.Authorisation.publication_state)
            )
        ),
        statuses=statuses,
        by_jurisdiction=_counts(
            db.execute(
                select(m.Authorisation.jurisdiction_code, func.count())
                .where(m.Authorisation.publication_state == "publiée")
                .group_by(m.Authorisation.jurisdiction_code)
            )
        ),
        proposals=_counts(
            db.execute(
                select(m.Proposal.state, func.count())
                .where(m.Proposal.state.notin_(["publiée", "archivée"]))
                .group_by(m.Proposal.state)
            )
        ),
        alerts_open=_counts(
            db.execute(
                select(m.SafetyNotice.level, func.count())
                .where(m.SafetyNotice.closed_at.is_(None))
                .group_by(m.SafetyNotice.level)
            )
        ),
        alerts_closed=db.scalar(select(func.count()).where(m.SafetyNotice.closed_at.is_not(None))) or 0,
        documents=db.scalar(select(func.count(m.SourceDocument.id))) or 0,
        accounts=accounts,
        accounts_inactive=db.scalar(select(func.count()).where(m.Account.active.is_(False))) or 0,
        copilot={
            "conversations": db.scalar(select(func.count(m.CopilotConversation.id))) or 0,
            "questions_30j": db.scalar(
                select(func.count())
                .where(m.CopilotMessage.role == "utilisateur")
                .where(m.CopilotMessage.known_at >= since)
            )
            or 0,
            "utile": feedback.get("utile", 0),
            "erreurs": feedback.get("erreur signalée", 0),
        },
        audit_last_7_days=db.scalar(
            select(func.count()).where(m.AuditEvent.created_at >= datetime.now(UTC) - timedelta(days=7))
        )
        or 0,
        audit_chain_intact=verify_chain(db) is None,
        as_of=day,
        permissions=permissions,
    )


# --- Comptes -----------------------------------------------------------------------------------------


class AccountOut(BaseModel):
    id: str
    login: str
    display_name: str
    roles: list[str]
    active: bool
    mfa_enabled: bool = False


class AccountIn(BaseModel):
    login: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=200)
    display_name: str = Field(min_length=2, max_length=120)
    roles: list[str] = Field(min_length=1)


class RolesIn(BaseModel):
    roles: list[str] = Field(min_length=1)


class ActiveIn(BaseModel):
    active: bool


class CreatedAccount(AccountOut):
    temporary_password: str  # affiché une seule fois


class PasswordOut(BaseModel):
    temporary_password: str


def _account_out(a: m.Account, mfa: set[str] | None = None) -> AccountOut:
    return AccountOut(
        id=a.id,
        login=a.login,
        display_name=a.display_name,
        roles=sorted(a.roles),
        active=a.active,
        mfa_enabled=a.id in (mfa or set()),
    )


def _mfa_enabled(db: DB) -> set[str]:
    return set(db.scalars(select(m.AccountMfa.account_id).where(m.AccountMfa.enabled_at.is_not(None))))


def _check_roles(roles: list[str]) -> list[str]:
    unknown = [r for r in roles if r not in ROLE_SLUGS.values()]
    if unknown:
        raise Problem(422, "validation", f"Rôle inconnu : {', '.join(unknown)}")
    return sorted(set(roles))


def _account(db: DB, account_id: str) -> m.Account:
    account = db.get(m.Account, account_id)
    if account is None:
        raise Problem(404, "not_found", "Compte inconnu")
    return account


def _directory(call: Any, *args: Any) -> None:
    try:
        call(*args)
    except DirectoryError as exc:
        raise Problem(409, "directory", str(exc)) from exc


@router.get("/roles", response_model=list[str])
def roles(actor: ActorDep) -> list[str]:
    _require(actor, READERS)
    return list(ROLE_SLUGS.values())


@router.get("/accounts", response_model=list[AccountOut])
def list_accounts(db: DB, actor: ActorDep) -> list[AccountOut]:
    _require(actor, READERS)
    mfa = _mfa_enabled(db)
    return [_account_out(a, mfa) for a in db.scalars(select(m.Account).order_by(m.Account.id))]


@router.post("/accounts", response_model=CreatedAccount, status_code=201)
def create_account(db: DB, actor: ActorDep, directory: DirectoryDep, body: AccountIn) -> CreatedAccount:
    _require(actor, ACCOUNT_MANAGERS)
    login = str(body.login).lower()
    if db.scalar(select(m.Account).where(m.Account.login == login)) is not None:
        raise Problem(409, "exists", "Un compte existe déjà avec cette adresse")
    roles = _check_roles(body.roles)
    numbers = [int(i.split("-")[1]) for i in db.scalars(select(m.Account.id)) if i.startswith("cpt-")]
    account = m.Account(
        id=f"cpt-{max(numbers, default=0) + 1:02d}", login=login, display_name=body.display_name, roles=roles
    )
    password = temporary_password()
    _directory(directory.create_user, login, body.display_name, roles, password)
    db.add(account)
    db.flush()
    record(
        db,
        actor=actor.id,
        action="account.created",
        object_type="account",
        object_id=account.id,
        after={"login": login, "roles": roles},
    )
    return CreatedAccount(**_account_out(account).model_dump(), temporary_password=password)


@router.put("/accounts/{account_id}/roles", response_model=AccountOut)
def set_roles(db: DB, actor: ActorDep, directory: DirectoryDep, account_id: str, body: RolesIn) -> AccountOut:
    _require(actor, ACCOUNT_MANAGERS)
    account = _account(db, account_id)
    roles = _check_roles(body.roles)
    if account.id == actor.id and not set(roles) & ACCOUNT_MANAGERS:
        raise Problem(409, "self", "Impossible de retirer son propre rôle d'administrateur")
    _directory(directory.set_roles, account.login, roles)
    record(
        db,
        actor=actor.id,
        action="account.roles_changed",
        object_type="account",
        object_id=account.id,
        before={"roles": sorted(account.roles)},
        after={"roles": roles},
    )
    account.roles = roles
    return _account_out(account)


@router.post("/accounts/{account_id}/active", response_model=AccountOut)
def set_active(db: DB, actor: ActorDep, directory: DirectoryDep, account_id: str, body: ActiveIn) -> AccountOut:
    _require(actor, ACCOUNT_MANAGERS)
    account = _account(db, account_id)
    if account.id == actor.id and not body.active:
        raise Problem(409, "self", "Impossible de désactiver son propre compte")
    _directory(directory.set_enabled, account.login, body.active)
    record(
        db,
        actor=actor.id,
        action="account.activated" if body.active else "account.deactivated",
        object_type="account",
        object_id=account.id,
        before={"active": account.active},
        after={"active": body.active},
    )
    account.active = body.active
    return _account_out(account)


@router.post("/accounts/{account_id}/password-reset", response_model=PasswordOut)
def reset_password(db: DB, actor: ActorDep, directory: DirectoryDep, account_id: str) -> PasswordOut:
    _require(actor, ACCOUNT_MANAGERS)
    account = _account(db, account_id)
    password = temporary_password()
    _directory(directory.reset_password, account.login, password)
    record(db, actor=actor.id, action="account.password_reset", object_type="account", object_id=account.id)
    return PasswordOut(temporary_password=password)


@router.post("/accounts/{account_id}/mfa-reset", response_model=AccountOut)
def reset_mfa(db: DB, actor: ActorDep, account_id: str) -> AccountOut:
    """Téléphone perdu : la double authentification est retirée, l'utilisateur la réactive à la connexion suivante."""
    _require(actor, ACCOUNT_MANAGERS)
    account = _account(db, account_id)
    row = db.get(m.AccountMfa, account.id)
    if row is None:
        raise Problem(409, "mfa_disabled", "Double authentification non activée pour ce compte")
    db.delete(row)
    record(db, actor=actor.id, action="mfa.reset", object_type="account", object_id=account.id)
    return _account_out(account)


# --- AMM ---------------------------------------------------------------------------------------------


class AuthorisationRow(BaseModel):
    id: str
    ma_number: str
    jurisdiction: str
    product: str
    holder: str
    publication_state: str
    status: str | None  # statut réglementaire, pour les AMM publiées
    last_verified_at: date
    dispute_open: bool


@router.get("/authorisations", response_model=list[AuthorisationRow])
def list_authorisations(
    db: DB,
    actor: ActorDep,
    state: str | None = None,
    jurisdiction: str | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> list[AuthorisationRow]:
    _require(actor, READERS)
    stmt = select(m.Authorisation).join(m.Product).order_by(m.Authorisation.jurisdiction_code, m.Authorisation.id)
    if state:
        stmt = stmt.where(m.Authorisation.publication_state == state)
    if jurisdiction:
        stmt = stmt.where(m.Authorisation.jurisdiction_code == jurisdiction)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            func.lower(m.Product.name).like(like)
            | func.lower(m.Product.designation).like(like)
            | func.lower(m.Authorisation.ma_number).like(like)
            | func.lower(m.Authorisation.holder).like(like)
        )
    day = today()
    return [
        AuthorisationRow(
            id=a.id,
            ma_number=a.ma_number,
            jurisdiction=a.jurisdiction_code,
            product=f"{a.product.name} — {a.product.designation}",
            holder=a.holder,
            publication_state=a.publication_state,
            status=_assess(a, day).status if a.publication_state == "publiée" else None,
            last_verified_at=a.last_verified_at,
            dispute_open=a.dispute_open,
        )
        for a in db.scalars(stmt).unique()
    ]


# --- Alertes -----------------------------------------------------------------------------------------


class AlertIn(BaseModel):
    type: Literal[
        "suspension d'AMM",
        "retrait d'AMM",
        "rappel de lot",
        "produit signalé falsifié ou sous-norme",
        "information de sécurité",
    ]
    level: Literal["rouge", "orange", "gris"]
    jurisdictions: list[str] = Field(min_length=1)
    authorisation_ids: list[str] = []
    batch_numbers: list[str] = []
    unlisted_product: str | None = None
    text: str = Field(min_length=10, max_length=2000)
    published_at: date | None = None


class CloseIn(BaseModel):
    reason: str = Field(min_length=5, max_length=500)
    closed_at: date | None = None


class AlertRow(BaseModel):
    id: str
    type: str
    level: str
    jurisdictions: list[str]
    authorisation_ids: list[str]
    batch_numbers: list[str]
    unlisted_product: str | None
    published_at: date
    closed_at: date | None
    text: str


def _alert_row(a: m.SafetyNotice) -> AlertRow:
    return AlertRow(
        id=a.id,
        type=a.type,
        level=a.level,
        jurisdictions=a.jurisdictions,
        authorisation_ids=a.authorisation_ids,
        batch_numbers=a.batch_numbers,
        unlisted_product=a.unlisted_product,
        published_at=a.published_at,
        closed_at=a.closed_at,
        text=a.text,
    )


@router.post("/alerts", response_model=AlertRow, status_code=201)
def create_alert(db: DB, actor: ActorDep, body: AlertIn) -> AlertRow:
    _require(actor, ALERT_MANAGERS)
    known = set(db.scalars(select(m.Jurisdiction.code)))
    if not set(body.jurisdictions) <= known:
        raise Problem(422, "validation", "Juridiction inconnue")
    for ma in body.authorisation_ids:
        if db.get(m.Authorisation, ma) is None:
            raise Problem(422, "validation", f"AMM inconnue : {ma}")
    numbers = [int(i.split("-")[1]) for i in db.scalars(select(m.SafetyNotice.id)) if i.startswith("alr-")]
    alert = m.SafetyNotice(
        id=f"alr-{max(numbers, default=0) + 1:03d}",
        type=body.type,
        level=body.level,
        jurisdictions=sorted(set(body.jurisdictions)),
        authorisation_ids=body.authorisation_ids,
        batch_numbers=body.batch_numbers,
        unlisted_product=body.unlisted_product or None,
        published_at=body.published_at or today(),
        text=body.text,
    )
    db.add(alert)
    db.flush()
    record(
        db,
        actor=actor.id,
        action="alert.published",
        object_type="alert",
        object_id=alert.id,
        after=_alert_row(alert).model_dump(mode="json"),
    )
    return _alert_row(alert)


@router.post("/alerts/{alert_id}/close", response_model=AlertRow)
def close_alert(db: DB, actor: ActorDep, alert_id: str, body: CloseIn) -> AlertRow:
    _require(actor, ALERT_MANAGERS)
    alert = db.get(m.SafetyNotice, alert_id)
    if alert is None:
        raise Problem(404, "not_found", "Alerte inconnue")
    if alert.closed_at is not None:
        raise Problem(409, "closed", "Alerte déjà close")
    alert.closed_at = body.closed_at or today()
    record(
        db,
        actor=actor.id,
        action="alert.closed",
        object_type="alert",
        object_id=alert.id,
        after={"closed_at": alert.closed_at.isoformat()},
        reason=body.reason,
    )
    return _alert_row(alert)


# --- Copilot -----------------------------------------------------------------------------------------


class FeedbackRow(BaseModel):
    message_id: str
    rating: str
    comment: str | None
    given_at: datetime
    account_id: str
    question: str | None
    answer: str
    model_id: str | None


@router.get("/copilot/feedback", response_model=list[FeedbackRow])
def copilot_feedback(db: DB, actor: ActorDep) -> list[FeedbackRow]:
    _require(actor, READERS)
    rows = db.execute(
        select(m.CopilotFeedback, m.CopilotMessage, m.CopilotConversation)
        .join(m.CopilotMessage, m.CopilotMessage.id == m.CopilotFeedback.message_id)
        .join(m.CopilotConversation, m.CopilotConversation.id == m.CopilotMessage.conversation_id)
        .order_by(m.CopilotFeedback.given_at.desc())
        .limit(200)
    ).all()
    out = []
    for fb, msg, conv in rows:
        question = db.scalar(
            select(m.CopilotMessage.content)
            .where(m.CopilotMessage.conversation_id == conv.id)
            .where(m.CopilotMessage.role == "utilisateur")
            .where(m.CopilotMessage.known_at <= msg.known_at)
            .order_by(m.CopilotMessage.known_at.desc())
            .limit(1)
        )
        out.append(
            FeedbackRow(
                message_id=str(msg.id),
                rating=fb.rating,
                comment=fb.comment,
                given_at=fb.given_at,
                account_id=conv.account_id,
                question=question,
                answer=msg.content,
                model_id=msg.model_id,
            )
        )
    return out


# --- Journal d'audit ---------------------------------------------------------------------------------


class AuditRow(BaseModel):
    seq: int
    actor: str
    action: str
    object_type: str
    object_id: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    reason: str | None
    created_at: datetime


class AuditPage(BaseModel):
    events: list[AuditRow]
    next_before: int | None  # pagination : passer ce numéro en `before`


@router.get("/audit", response_model=AuditPage)
def audit(
    db: DB,
    actor: ActorDep,
    before: int | None = None,
    object_type: str | None = None,
    who: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> AuditPage:
    _require(actor, READERS)
    stmt = select(m.AuditEvent).order_by(m.AuditEvent.seq.desc()).limit(limit + 1)
    if before is not None:
        stmt = stmt.where(m.AuditEvent.seq < before)
    if object_type:
        stmt = stmt.where(m.AuditEvent.object_type == object_type)
    if who:
        stmt = stmt.where(m.AuditEvent.actor == who)
    rows = list(db.scalars(stmt))
    more = len(rows) > limit
    rows = rows[:limit]
    return AuditPage(
        events=[
            AuditRow(
                seq=e.seq,
                actor=e.actor,
                action=e.action,
                object_type=e.object_type,
                object_id=e.object_id,
                before=e.before,
                after=e.after,
                reason=e.reason,
                created_at=e.created_at,
            )
            for e in rows
        ],
        next_before=rows[-1].seq if more and rows else None,
    )
