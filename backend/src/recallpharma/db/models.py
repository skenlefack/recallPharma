"""Schéma `reg` (référentiel partagé) et `integration` (audit) du prototype.

Noms alignés sur le schéma de référence du dossier v3. Écart voulu : aucune colonne de statut d'AMM,
le statut est toujours calculé par le moteur de règles (RG-03).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


REG = {"schema": "reg"}


class Jurisdiction(Base):
    __tablename__ = "jurisdiction"
    __table_args__ = (CheckConstraint("kind IN ('pays','communauté')", name="kind"), REG)

    code: Mapped[str] = mapped_column(String(8), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(Text)
    validity_years: Mapped[int | None] = mapped_column(Integer)  # NULL : durée illimitée (RG-04)
    members: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    banned_list_status: Mapped[str] = mapped_column(Text, server_default="liste nationale non communiquée")
    banned_substances: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")


class Organisation(Base):
    __tablename__ = "organisation"
    __table_args__ = (REG,)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True)
    country: Mapped[str | None] = mapped_column(Text)


class Substance(Base):
    __tablename__ = "substance"
    __table_args__ = (REG,)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    inn_name: Mapped[str] = mapped_column(Text, unique=True)
    atcvet_code: Mapped[str | None] = mapped_column(Text)
    is_antimicrobial: Mapped[bool] = mapped_column(Boolean, server_default="false")
    who_category: Mapped[str | None] = mapped_column(Text)
    woah_category: Mapped[str | None] = mapped_column(Text)
    codex_rmr: Mapped[bool] = mapped_column(Boolean, server_default="false")


class Product(Base):
    """RG-02 : dénomination + forme + composition ; un changement de forme ou de teneur = nouveau produit."""

    __tablename__ = "product"
    __table_args__ = (REG,)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    designation: Mapped[str] = mapped_column(Text)
    pharmaceutical_form: Mapped[str] = mapped_column(Text)
    product_type: Mapped[str] = mapped_column(Text)
    routes: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    target_species: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")

    components: Mapped[list[ProductComponent]] = relationship(back_populates="product", lazy="selectin")


class ProductComponent(Base):
    __tablename__ = "product_component"
    __table_args__ = (
        CheckConstraint(
            "is_ambiguous OR (strength_value IS NOT NULL AND strength_unit IS NOT NULL AND strength_basis IS NOT NULL)",
            name="normalised_or_ambiguous",
        ),
        REG,
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("reg.product.id"))
    substance_id: Mapped[str] = mapped_column(ForeignKey("reg.substance.id"))
    strength_as_stated: Mapped[str] = mapped_column(Text)  # RG-07 : toujours conservée
    strength_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 8))
    strength_unit: Mapped[str | None] = mapped_column(Text)
    strength_basis: Mapped[str | None] = mapped_column(Text)
    is_ambiguous: Mapped[bool] = mapped_column(Boolean)

    product: Mapped[Product] = relationship(back_populates="components")
    substance: Mapped[Substance] = relationship(lazy="joined")


class SourceDocument(Base):
    """Document source immuable ; l'empreinte SHA-256 est posée à la capture (M01)."""

    __tablename__ = "source_document"
    __table_args__ = (CheckConstraint("nature IN ('officielle','déclarative')", name="nature"), REG)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nature: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    document_date: Mapped[date] = mapped_column(Date)
    latest_edition: Mapped[bool] = mapped_column(Boolean)
    sha256: Mapped[str | None] = mapped_column(String(64), unique=True)
    storage_key: Mapped[str | None] = mapped_column(Text)
    filename: Mapped[str | None] = mapped_column(Text)
    media_type: Mapped[str | None] = mapped_column(Text)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    replaces_document_id: Mapped[int | None] = mapped_column(ForeignKey("reg.source_document.id"))
    uploaded_by: Mapped[str | None] = mapped_column(ForeignKey("core.account.id"))
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Authorisation(Base):
    __tablename__ = "authorisation"
    __table_args__ = (
        UniqueConstraint("jurisdiction_code", "ma_number_normalized", name="jurisdiction_number"),  # RG-01
        CheckConstraint("procedure IN ('nationale','communautaire')", name="procedure"),
        CheckConstraint(
            "publication_state IN ('proposée','en première validation','en seconde validation',"
            "'en litige','publiée','archivée')",
            name="publication_state",
        ),
        CheckConstraint("validations >= 0", name="validations"),
        REG,
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    jurisdiction_code: Mapped[str] = mapped_column(ForeignKey("reg.jurisdiction.code"))
    ma_number: Mapped[str] = mapped_column(Text)
    ma_number_normalized: Mapped[str] = mapped_column(Text)
    product_id: Mapped[str] = mapped_column(ForeignKey("reg.product.id"))
    procedure: Mapped[str] = mapped_column(Text)
    holder: Mapped[str] = mapped_column(Text)
    manufacturer: Mapped[str | None] = mapped_column(Text)
    dispensing_condition: Mapped[str | None] = mapped_column(Text)
    grant_date: Mapped[date] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    expiry_is_computed: Mapped[bool] = mapped_column(Boolean, server_default="false")
    source_document_id: Mapped[int | None] = mapped_column(ForeignKey("reg.source_document.id"))
    validations: Mapped[int] = mapped_column(Integer, server_default="0")
    last_verified_at: Mapped[date] = mapped_column(Date)
    dispute_open: Mapped[bool] = mapped_column(Boolean, server_default="false")
    renewal_pending: Mapped[bool] = mapped_column(Boolean, server_default="false")
    publication_state: Mapped[str] = mapped_column(Text, server_default="proposée")

    jurisdiction: Mapped[Jurisdiction] = relationship(lazy="joined")
    product: Mapped[Product] = relationship(lazy="joined")
    source: Mapped[SourceDocument | None] = relationship(lazy="joined")
    events: Mapped[list[RegulatoryEvent]] = relationship(lazy="selectin", order_by="RegulatoryEvent.effective_date")
    spc_versions: Mapped[list[SpcVersion]] = relationship(lazy="selectin", order_by="SpcVersion.id")


class RegulatoryEvent(Base):
    """Événements réglementaires, en ajout seul ; `recorded_at` est le temps de connaissance (ADR-08)."""

    __tablename__ = "regulatory_event"
    __table_args__ = (
        CheckConstraint(
            "type NOT IN ('suspension','retrait d''office','interdiction') OR reason IS NOT NULL",
            name="reason_required",  # RG-15 : motif obligatoire (« non communiqué » accepté)
        ),
        REG,
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    authorisation_id: Mapped[str] = mapped_column(ForeignKey("reg.authorisation.id"), index=True)
    type: Mapped[str] = mapped_column(Text)
    decision_date: Mapped[date] = mapped_column(Date)
    effective_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(Text)
    new_expiry_date: Mapped[date | None] = mapped_column(Date)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SpcVersion(Base):
    __tablename__ = "spc_version"
    __table_args__ = (UniqueConstraint("authorisation_id", "version_label", name="label"), REG)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    authorisation_id: Mapped[str] = mapped_column(ForeignKey("reg.authorisation.id"), index=True)
    version_label: Mapped[str] = mapped_column(Text)
    languages: Mapped[list[str]] = mapped_column(ARRAY(Text))
    restrictions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default="[]")
    posology: Mapped[str | None] = mapped_column(Text)
    contraindications: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    proposal_id: Mapped[int | None] = mapped_column(ForeignKey("reg.proposal.id"))

    withdrawal_periods: Mapped[list[WithdrawalPeriod]] = relationship(lazy="selectin")


class WithdrawalPeriod(Base):
    """RG-08 : valeur (y compris zéro), interdit, non renseigné, conditionnel, sans objet."""

    __tablename__ = "withdrawal_period"
    __table_args__ = (
        CheckConstraint("kind IN ('valeur','interdit','non renseigné','conditionnel','sans objet')", name="kind"),
        CheckConstraint("unit IS NULL OR unit IN ('heure','jour','degré-jour','traite')", name="unit"),
        CheckConstraint(
            "(kind = 'valeur' AND value IS NOT NULL AND value >= 0 AND unit IS NOT NULL) "
            "OR (kind <> 'valeur' AND value IS NULL AND unit IS NULL)",
            name="value_iff_valeur",
        ),
        REG,
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    spc_version_id: Mapped[int] = mapped_column(ForeignKey("reg.spc_version.id"), index=True)
    species: Mapped[str] = mapped_column(Text)
    commodity: Mapped[str] = mapped_column(Text)
    route: Mapped[str | None] = mapped_column(Text)
    dose_condition: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text)
    value: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    unit: Mapped[str | None] = mapped_column(Text)
    spc_text: Mapped[str | None] = mapped_column(Text)


class SafetyNotice(Base):
    """Alertes : suspensions, retraits, rappels de lots, produits falsifiés, informations de sécurité (M06)."""

    __tablename__ = "safety_notice"
    __table_args__ = (CheckConstraint("level IN ('rouge','orange','gris')", name="level"), REG)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    type: Mapped[str] = mapped_column(Text)
    level: Mapped[str] = mapped_column(Text)
    jurisdictions: Mapped[list[str]] = mapped_column(ARRAY(Text))
    authorisation_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    batch_numbers: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default="{}")
    unlisted_product: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[date] = mapped_column(Date)
    closed_at: Mapped[date | None] = mapped_column(Date)
    text: Mapped[str] = mapped_column(Text)


class Account(Base):
    """Compte et rôles. Prototype : identité locale ; Keycloak (OIDC) la remplacera sans changer les rôles."""

    __tablename__ = "account"
    __table_args__ = ({"schema": "core"},)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    login: Mapped[str] = mapped_column(Text, unique=True)
    display_name: Mapped[str] = mapped_column(Text)
    roles: Mapped[list[str]] = mapped_column(ARRAY(Text))
    active: Mapped[bool] = mapped_column(Boolean, server_default="true")


class Proposal(Base):
    """Proposition de fiche (création ou mise à jour d'une AMM) qui suit le circuit A → B → C (M02)."""

    __tablename__ = "proposal"
    __table_args__ = (
        CheckConstraint(
            "state IN ('proposée','en première validation','en seconde validation','en litige','publiée','archivée')",
            name="state",
        ),
        CheckConstraint("first_validator IS NULL OR first_validator <> prepared_by", name="b_not_a"),
        CheckConstraint(
            "second_validator IS NULL OR (second_validator <> prepared_by AND second_validator <> first_validator)",
            name="c_not_a_b",
        ),
        CheckConstraint(
            "arbiter IS NULL OR (arbiter <> prepared_by AND arbiter <> first_validator "
            "AND arbiter <> second_validator AND arbitration_reason IS NOT NULL)",
            name="arbiter_independent",
        ),
        REG,
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    authorisation_id: Mapped[str | None] = mapped_column(ForeignKey("reg.authorisation.id"), index=True)
    state: Mapped[str] = mapped_column(Text, server_default="proposée")
    origin: Mapped[str] = mapped_column(Text, server_default="saisie")  # saisie, import, extraction
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    prepared_by: Mapped[str] = mapped_column(ForeignKey("core.account.id"))
    first_validator: Mapped[str | None] = mapped_column(ForeignKey("core.account.id"))
    second_validator: Mapped[str | None] = mapped_column(ForeignKey("core.account.id"))
    blind_entry: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    discrepancies: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    arbiter: Mapped[str | None] = mapped_column(ForeignKey("core.account.id"))
    arbitration_decision: Mapped[str | None] = mapped_column(Text)
    arbitration_reason: Mapped[str | None] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProposalStep(Base):
    """Historique en ajout seul des actions sur une proposition (champ, valeur proposée, valeur retenue)."""

    __tablename__ = "proposal_step"
    __table_args__ = (REG,)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    proposal_id: Mapped[int] = mapped_column(ForeignKey("reg.proposal.id"), index=True)
    actor: Mapped[str] = mapped_column(ForeignKey("core.account.id"))
    action: Mapped[str] = mapped_column(Text)
    from_state: Mapped[str] = mapped_column(Text)
    to_state: Mapped[str] = mapped_column(Text)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SourceView(Base):
    """Trace qu'un validateur a affiché la page source d'un champ avant de le confirmer (CT-VAL-01)."""

    __tablename__ = "source_view"
    __table_args__ = (REG,)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    proposal_id: Mapped[int] = mapped_column(ForeignKey("reg.proposal.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    actor: Mapped[str] = mapped_column(ForeignKey("core.account.id"))
    field: Mapped[str] = mapped_column(Text)
    document_id: Mapped[int] = mapped_column(ForeignKey("reg.source_document.id"))
    page: Mapped[int] = mapped_column(Integer)
    viewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditEvent(Base):
    """RG-33 : journal en ajout seul, chaîné par SHA-256 (`prev_hash` → `hash`)."""

    __tablename__ = "audit_event"
    __table_args__ = ({"schema": "integration"},)

    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text)
    object_type: Mapped[str] = mapped_column(Text)
    object_id: Mapped[str] = mapped_column(Text)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)
