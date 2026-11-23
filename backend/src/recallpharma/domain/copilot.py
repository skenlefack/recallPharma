"""Copilot : filtrage des questions, contrôle après génération et composition déterministe (RG-23 à RG-26, D6).

Le modèle ne rédige aucun fait. Il écrit des phrases de liaison et désigne les valeurs par des références
[[enregistrement:champ]] ; la passerelle insère elle-même chaque valeur depuis les résultats d'outils du tour.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date

ABSTENTION = (
    "RecallPharma ne dispose pas de données vérifiées pour répondre à cette question dans la juridiction choisie."
)
ABSTENTION_EN = "RecallPharma has no verified data to answer this question in the selected jurisdiction."
MENTION = "Information réglementaire. Ne remplace pas le jugement clinique du vétérinaire."
MENTION_EN = "Regulatory information. Does not replace the veterinarian's clinical judgement."
CHECK_FAILED = "La réponse rédigée n'a pas passé le contrôle : seuls les enregistrements du registre sont affichés."
CHECK_FAILED_EN = "The drafted answer failed the check: only the registry records are shown."
UNAVAILABLE = "Copilot momentanément indisponible. La recherche du registre reste disponible."

REF = re.compile(r"\[\[([^\[\]:]+):([^\[\]]+)\]\]")
EVIDENCE_ORDER = "ABCD"  # du plus fort au plus faible


def normalise(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


# --- Réception (RG-25) -------------------------------------------------------------------------

_OUT_OF_SCOPE = {
    "diagnostic": (
        r"\bdiagnosti",
        r"\bde quoi (souffre|est atteint)",
        r"\bquelle maladie\b",
        r"\bquel traitement (choisir|donner|prescrire)",
        r"\bque (dois-je|faut-il) (lui )?(donner|prescrire)",
        r"\bwhat disease\b",
        r"\bdiagnos(e|is)\b",
        r"\bwhich treatment should\b",
    ),
    "médicament humain": (
        r"\b(pour|a) (un |une )?(humain|enfant|bebe|femme enceinte|moi-meme)\b",
        r"\bmedicament humain\b",
        r"\bfor (a |my )?(human|child|baby)\b",
        r"\bhuman (medicine|use)\b",
    ),
}
_INJECTION = (
    r"\bignore[rz]? (les|toutes|tes|vos|the|all|previous|prior)\b",
    r"\boublie[rz]? (les|tes|vos) (instructions|consignes|regles)",
    r"\b(system|systeme) ?prompt\b",
    r"\btu es (maintenant|desormais)\b",
    r"\byou are now\b",
    r"\b(supprime|modifie|publie|valide|efface)[rz]? (la|les|cette) (fiche|amm|proposition|donnee)",
)


def screen_question(text: str) -> str | None:
    """Motif d'abstention immédiate, sans appel au modèle : diagnostic, choix thérapeutique ou médicament humain."""
    t = normalise(text)
    for reason, patterns in _OUT_OF_SCOPE.items():
        if any(re.search(p, t) for p in patterns):
            return reason
    return None


def looks_like_injection(text: str) -> bool:
    """Tentative d'instruction cachée (ENF-SEC-05) : signalée au journal ; le comportement reste inchangé."""
    t = normalise(text)
    return any(re.search(p, t) for p in _INJECTION)


def detect_language(text: str) -> str:
    words = re.findall(r"[a-z']+", normalise(text))
    english = {"the", "which", "what", "are", "is", "for", "in", "with", "products", "authorised", "authorized", "how"}
    french = {"le", "la", "les", "des", "quels", "quelles", "est", "pour", "dans", "avec", "produits", "autorises"}
    return "en" if sum(w in english for w in words) > sum(w in french for w in words) else "fr"


# --- Contrôle après génération (RG-23) ---------------------------------------------------------

Records = Mapping[str, Mapping[str, str]]


@dataclass(frozen=True, slots=True)
class CheckResult:
    passed: bool
    problems: tuple[str, ...]
    refs: tuple[tuple[str, str], ...]


def check_draft(draft: str, records: Records, closed_terms: Iterable[str]) -> CheckResult:
    """Toute référence désigne un enregistrement et un champ du tour ; hors références, le texte ne contient ni chiffre,
    ni terme des listes fermées (substances, espèces, statuts) ; une réponse sans référence échoue."""
    problems: list[str] = []
    refs = tuple((r.strip(), f.strip()) for r, f in REF.findall(draft))
    for record, fld in refs:
        if record not in records:
            problems.append(f"référence à un enregistrement absent : {record}")
        elif fld not in records[record]:
            problems.append(f"champ absent : {record}:{fld}")
    if not refs:
        problems.append("aucune référence à un enregistrement")
    free = normalise(REF.sub(" ", draft))
    if re.search(r"\d", free):
        problems.append("chiffre hors référence")
    for term in sorted({normalise(t) for t in closed_terms if t.strip()}):
        if re.search(rf"(?<![\w-]){re.escape(term)}(?![\w-])", free):
            problems.append(f"terme réservé hors référence : {term}")
    return CheckResult(not problems, tuple(problems), refs)


def render(draft: str, records: Records) -> str:
    return REF.sub(lambda m: records[m.group(1).strip()][m.group(2).strip()], draft).strip()


# --- Composition (RG-26) -----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Context:
    jurisdiction: str
    oldest_verification: date | None
    weakest_evidence: str | None
    sources: tuple[str, ...] = field(default=())

    def line(self, language: str = "fr") -> str:
        if self.oldest_verification is None and self.weakest_evidence is None:
            return f"Jurisdiction: {self.jurisdiction}" if language == "en" else f"Juridiction : {self.jurisdiction}"
        if language == "en":
            return (
                f"Jurisdiction: {self.jurisdiction} · oldest verification: {self.oldest_verification or 'unknown'}"
                f" · weakest evidence level: {self.weakest_evidence or 'none'}"
            )
        return (
            f"Juridiction : {self.jurisdiction} · vérification la plus ancienne : "
            f"{self.oldest_verification or 'inconnue'} · niveau de preuve le plus faible : "
            f"{self.weakest_evidence or '—'}"
        )


def weakest(levels: Iterable[str]) -> str | None:
    known = [lv for lv in levels if lv in EVIDENCE_ORDER]
    return max(known, key=EVIDENCE_ORDER.index) if known else None


def context(
    jurisdiction: str, verified: Iterable[date | None], levels: Iterable[str], sources: Iterable[str]
) -> Context:
    dates = [d for d in verified if d is not None]
    return Context(jurisdiction, min(dates) if dates else None, weakest(levels), tuple(dict.fromkeys(sources)))
