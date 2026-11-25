"""Circuit de validation A → B → C, litige et arbitrage (M02 ; RG-07, RG-09 à RG-12, RG-32).

A prépare, B valide champ par champ contre le document, C ressaisit à l'aveugle les champs à risque.
A, B et C sont trois personnes distinctes ; toute modification après signature remet la revue à zéro.
Fonctions pures : la persistance et la publication sont faites par la couche base.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

from recallpharma.domain.identifiers import normalise_ma_number


class ProposalState(StrEnum):
    PROPOSED = "proposée"
    FIRST_REVIEW = "en première validation"
    SECOND_REVIEW = "en seconde validation"
    DISPUTED = "en litige"
    PUBLISHED = "publiée"
    ARCHIVED = "archivée"


FINAL_STATES = frozenset({ProposalState.PUBLISHED, ProposalState.ARCHIVED})


class Role(StrEnum):
    VALIDATOR = "Validateur"
    REGULATORY_LEAD = "Responsable réglementaire"
    PRODUCT_LEAD = "Responsable produit"
    TECH_ADMIN = "Administrateur technique"
    FUNCTIONAL_ADMIN = "Administrateur fonctionnel"


#: Rôles qui peuvent préparer et valider des données (RG-32 : jamais l'administrateur technique).
CURATOR_ROLES = frozenset({Role.VALIDATOR, Role.REGULATORY_LEAD})
#: Rôles soumis à la double authentification obligatoire : ceux qui valident ou administrent.
MFA_REQUIRED_ROLES = (Role.VALIDATOR, Role.REGULATORY_LEAD, Role.TECH_ADMIN, Role.FUNCTIONAL_ADMIN)


@dataclass(frozen=True, slots=True)
class Actor:
    id: str
    roles: frozenset[str]

    def has(self, *roles: Role) -> bool:
        return any(r.value in self.roles for r in roles)


class WorkflowError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# --- Champs critiques (RG-09) -------------------------------------------------------------------


def _get(path: str) -> Callable[[Mapping[str, Any]], Any]:
    keys = path.split(".")

    def getter(payload: Mapping[str, Any]) -> Any:
        node: Any = payload
        for k in keys:
            if not isinstance(node, Mapping):
                return None
            node = node.get(k)
        return node

    return getter


def _prohibitions(payload: Mapping[str, Any]) -> Any:
    restrictions = _get("spc.restrictions")(payload)
    return [r for r in restrictions or [] if r.get("type") == "interdiction"] if restrictions is not None else None


@dataclass(frozen=True, slots=True)
class CriticalField:
    key: str
    label: str
    read: Callable[[Mapping[str, Any]], Any]
    may_be_empty: bool = False  # une liste vide est une valeur (« aucune interdiction »), pas une absence


CRITICAL_FIELDS: tuple[CriticalField, ...] = (
    CriticalField("denomination", "Dénomination", _get("product.name")),
    CriticalField("ma_number", "Numéro d'AMM", _get("ma_number")),
    CriticalField("jurisdiction", "Juridiction", _get("jurisdiction")),
    CriticalField("events", "Événements et dates", _get("events")),
    CriticalField("holder", "Titulaire", _get("holder")),
    CriticalField("components", "Substances et teneurs", _get("product.components")),
    CriticalField("pharmaceutical_form", "Forme pharmaceutique", _get("product.pharmaceutical_form")),
    CriticalField("routes", "Voies d'administration", _get("product.routes")),
    CriticalField("target_species", "Espèces cibles", _get("product.target_species")),
    CriticalField("posology", "Posologie", _get("spc.posology")),
    CriticalField("withdrawal_periods", "Délais d'attente", _get("spc.withdrawal_periods")),
    CriticalField("prohibitions", "Interdictions", _prohibitions, may_be_empty=True),
    CriticalField("contraindications", "Contre-indications", _get("spc.contraindications"), may_be_empty=True),
    CriticalField("dispensing_condition", "Conditions de délivrance", _get("dispensing_condition")),
)
CRITICAL_KEYS = frozenset(f.key for f in CRITICAL_FIELDS)

#: RG-10 : ressaisis à l'aveugle par le second validateur.
BLIND_FIELDS = ("ma_number", "components", "posology", "withdrawal_periods")


@dataclass(frozen=True, slots=True)
class Issue:
    field: str
    code: str
    message: str


def _is_blank(value: Any, may_be_empty: bool) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, list | tuple):
        return not value and not may_be_empty
    return False


def publication_issues(payload: Mapping[str, Any], provenance: Mapping[str, Any]) -> list[Issue]:
    """Ce qui empêche la publication : champ critique absent, valeur sans source (RG-12),
    teneur ambiguë (RG-07)."""
    issues: list[Issue] = []
    for f in CRITICAL_FIELDS:
        if _is_blank(f.read(payload), f.may_be_empty):
            issues.append(Issue(f.key, "missing", f"{f.label} : valeur absente"))
            continue
        ref = provenance.get(f.key)
        if not isinstance(ref, Mapping) or ref.get("document_id") is None or not ref.get("page"):
            issues.append(Issue(f.key, "no_source", f"{f.label} : aucune source (document et page) citée"))
    for i, c in enumerate(_get("product.components")(payload) or []):
        if c.get("strength_value") is None or not c.get("strength_unit") or not c.get("strength_basis"):
            issues.append(
                Issue(
                    "components",
                    "ambiguous_strength",
                    f"Teneur n° {i + 1} « {c.get('strength_as_stated')} » sans base déclarée : publication bloquée",
                )
            )
    return issues


def changed_critical_fields(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[str]:
    return [f.key for f in CRITICAL_FIELDS if f.read(before) != f.read(after)]


def mask_blind_fields(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Vue du second validateur : les champs à ressaisir sont masqués."""
    masked = {k: v for k, v in payload.items()}
    masked["ma_number"] = None
    product = dict(masked.get("product") or {})
    product["components"] = [{"substance_id": c.get("substance_id")} for c in (product.get("components") or [])]
    masked["product"] = product
    spc = dict(masked.get("spc") or {})
    spc["posology"] = None
    spc["withdrawal_periods"] = None
    masked["spc"] = spc
    return masked


# --- Comparaison de la ressaisie à l'aveugle (RG-10) ---------------------------------------------

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


def _canon_number(match: re.Match[str]) -> str:
    try:
        n = Decimal(match.group(0).replace(",", "."))
    except InvalidOperation:  # pragma: no cover - l'expression ne capture que des nombres
        return match.group(0)
    text = format(n.normalize(), "f")
    return text


def normalise_text(value: Any) -> str:
    """Casse, espaces et écriture des nombres ignorés : « 100,0 mg/ml » = « 100 mg/mL »."""
    text = " ".join(str(value or "").lower().split())
    text = _NUMBER.sub(_canon_number, text)
    return text.replace(" ", "")


def canonical_number(value: Any) -> str | None:
    if value is None or value == "":
        return None
    try:
        return format(Decimal(str(value)).normalize(), "f")
    except InvalidOperation:
        return normalise_text(value)


def _strengths(components: Iterable[Mapping[str, Any]] | None) -> dict[str, str]:
    return {str(c.get("substance_id")): normalise_text(c.get("strength_as_stated")) for c in components or []}


def _withdrawals(periods: Iterable[Mapping[str, Any]] | None) -> set[tuple[str | None, ...]]:
    return {
        (
            normalise_text(w.get("species")),
            normalise_text(w.get("commodity")),
            normalise_text(w.get("route")) if w.get("route") else None,
            w.get("kind"),
            canonical_number(w.get("value")),
            w.get("unit"),
        )
        for w in periods or []
    }


@dataclass(frozen=True, slots=True)
class Discrepancy:
    field: str
    prepared: Any
    entered: Any


def compare_blind_entry(payload: Mapping[str, Any], blind: Mapping[str, Any]) -> list[Discrepancy]:
    out: list[Discrepancy] = []
    if normalise_ma_number(str(payload.get("ma_number") or "")) != normalise_ma_number(
        str(blind.get("ma_number") or "")
    ):
        out.append(Discrepancy("ma_number", payload.get("ma_number"), blind.get("ma_number")))
    prepared_components = _get("product.components")(payload)
    if _strengths(prepared_components) != _strengths(blind.get("components")):
        out.append(Discrepancy("components", prepared_components, blind.get("components")))
    prepared_posology = _get("spc.posology")(payload)
    if normalise_text(prepared_posology) != normalise_text(blind.get("posology")):
        out.append(Discrepancy("posology", prepared_posology, blind.get("posology")))
    prepared_periods = _get("spc.withdrawal_periods")(payload)
    if _withdrawals(prepared_periods) != _withdrawals(blind.get("withdrawal_periods")):
        out.append(Discrepancy("withdrawal_periods", prepared_periods, blind.get("withdrawal_periods")))
    return out


def apply_blind_values(payload: Mapping[str, Any], blind: Mapping[str, Any], fields: Iterable[str]) -> dict[str, Any]:
    """Arbitrage en faveur de la ressaisie : les valeurs de C remplacent celles de A pour ces champs."""
    out: dict[str, Any] = {
        **payload,
        "product": dict(payload.get("product") or {}),
        "spc": dict(payload.get("spc") or {}),
    }
    for f in fields:
        if f == "ma_number":
            out["ma_number"] = blind["ma_number"]
        elif f == "components":
            entered = {str(c["substance_id"]): c for c in blind["components"]}
            out["product"]["components"] = [
                {**c, **entered.get(str(c.get("substance_id")), {})} for c in out["product"].get("components", [])
            ]
        elif f == "posology":
            out["spc"]["posology"] = blind["posology"]
        elif f == "withdrawal_periods":
            out["spc"]["withdrawal_periods"] = blind["withdrawal_periods"]
    return out


# --- Transitions ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ProposalSnapshot:
    state: ProposalState
    prepared_by: str
    first_validator: str | None = None
    second_validator: str | None = None


def _require_curator(actor: Actor) -> None:
    if actor.has(Role.TECH_ADMIN):
        raise WorkflowError(
            "tech_admin_cannot_validate", "Un administrateur technique ne valide jamais de données (RG-32)"
        )
    if not actor.has(*CURATOR_ROLES):
        raise WorkflowError("forbidden", "Rôle de validation requis")


def _require_state(p: ProposalSnapshot, *states: ProposalState) -> None:
    if p.state not in states:
        raise WorkflowError("invalid_state", f"Action impossible à l'état « {p.state.value} »")


def check_prepare(actor: Actor) -> None:
    _require_curator(actor)


def check_edit(p: ProposalSnapshot, actor: Actor) -> ProposalState:
    """Seul le préparateur modifie ; une modification après signature remet la revue à zéro."""
    _require_curator(actor)
    if p.state in FINAL_STATES:
        raise WorkflowError("invalid_state", "Une fiche publiée ou archivée ne se modifie pas : créer une proposition")
    if actor.id != p.prepared_by:
        raise WorkflowError("not_preparer", "Seul le préparateur modifie sa proposition")
    return ProposalState.PROPOSED


def check_submit(p: ProposalSnapshot, actor: Actor, issues: list[Issue]) -> ProposalState:
    _require_curator(actor)
    _require_state(p, ProposalState.PROPOSED)
    if actor.id != p.prepared_by:
        raise WorkflowError("not_preparer", "Seul le préparateur soumet sa proposition")
    if issues:
        raise WorkflowError("incomplete", "Proposition incomplète : " + " ; ".join(i.message for i in issues))
    return ProposalState.FIRST_REVIEW


def check_first_validation(
    p: ProposalSnapshot,
    actor: Actor,
    approve: bool,
    confirmed: Iterable[str],
    viewed: Iterable[str],
    reason: str | None,
) -> ProposalState:
    """B confirme chaque champ critique après avoir affiché sa page source (CT-VAL-01), ou renvoie à A."""
    _require_curator(actor)
    _require_state(p, ProposalState.FIRST_REVIEW)
    if actor.id == p.prepared_by:
        raise WorkflowError("same_person", "Le préparateur ne valide pas sa propre saisie (RG-32)")
    if not approve:
        if not (reason and reason.strip()):
            raise WorkflowError("reason_required", "Un renvoi au préparateur doit être motivé")
        return ProposalState.PROPOSED
    missing = CRITICAL_KEYS - set(confirmed)
    if missing:
        raise WorkflowError("unconfirmed_fields", "Champs critiques non confirmés : " + ", ".join(sorted(missing)))
    unseen = CRITICAL_KEYS - set(viewed)
    if unseen:
        raise WorkflowError(
            "source_not_viewed", "Confirmation refusée : page source non affichée pour " + ", ".join(sorted(unseen))
        )
    return ProposalState.SECOND_REVIEW


def check_blind_entry(p: ProposalSnapshot, actor: Actor, discrepancies: list[Discrepancy]) -> ProposalState:
    _require_curator(actor)
    _require_state(p, ProposalState.SECOND_REVIEW)
    if actor.id in (p.prepared_by, p.first_validator):
        raise WorkflowError(
            "same_person", "Le second validateur doit être distinct du préparateur et du premier validateur (RG-32)"
        )
    return ProposalState.DISPUTED if discrepancies else ProposalState.PUBLISHED


class ArbitrationDecision(StrEnum):
    KEEP_PREPARED = "retenir la préparation"
    KEEP_BLIND = "retenir la ressaisie"
    REJECT = "rejeter"


def check_arbitration(
    p: ProposalSnapshot, actor: Actor, decision: ArbitrationDecision, reason: str | None
) -> ProposalState:
    """RG-11 : le responsable réglementaire arbitre s'il n'est aucun des validateurs de la fiche,
    sinon le responsable produit."""
    _require_state(p, ProposalState.DISPUTED)
    if actor.has(Role.TECH_ADMIN):
        raise WorkflowError("tech_admin_cannot_validate", "Un administrateur technique n'arbitre pas (RG-32)")
    if actor.id in (p.prepared_by, p.first_validator, p.second_validator):
        raise WorkflowError(
            "arbiter_involved",
            "L'arbitre n'est aucun des acteurs de la fiche : un autre responsable réglementaire ou le responsable "
            "produit arbitre",
        )
    if not actor.has(Role.REGULATORY_LEAD, Role.PRODUCT_LEAD):
        raise WorkflowError("forbidden", "Arbitrage réservé au responsable réglementaire ou au responsable produit")
    if not (reason and reason.strip()):
        raise WorkflowError("reason_required", "L'arbitrage doit être motivé")
    return ProposalState.ARCHIVED if decision is ArbitrationDecision.REJECT else ProposalState.PUBLISHED
