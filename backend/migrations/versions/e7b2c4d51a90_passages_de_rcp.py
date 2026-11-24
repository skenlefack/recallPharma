"""Rubriques et passages de RCP : plein texte (colonne calculée) et plongements (pgvector) pour la recherche hybride.

Revision ID: e7b2c4d51a90
Revises: d4e1a7c93b20
Create Date: 2026-11-24 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e7b2c4d51a90"
down_revision: str | Sequence[str] | None = "d4e1a7c93b20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TSV = (
    "to_tsvector('french'::regconfig, reg.f_unaccent(heading || ' ' || text)) || "
    "to_tsvector('english'::regconfig, reg.f_unaccent(heading || ' ' || text))"
)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "spc_section",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("spc_version_id", sa.Integer(), nullable=False),
        sa.Column("rubric", sa.Text(), nullable=False),
        sa.Column("language", sa.String(length=2), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("source_title", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["spc_version_id"], ["reg.spc_version.id"], name=op.f("fk_spc_section_spc_version_id_spc_version")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_spc_section")),
        sa.UniqueConstraint("spc_version_id", "rubric", "language", name="rubric"),
        schema="reg",
    )
    op.create_index(op.f("ix_reg_spc_section_spc_version_id"), "spc_section", ["spc_version_id"], schema="reg")
    op.create_table(
        "spc_passage",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("section_id", sa.Integer(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("heading", sa.Text(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("tsv", postgresql.TSVECTOR(), sa.Computed(TSV, persisted=True), nullable=True),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column("embedding_model", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["section_id"], ["reg.spc_section.id"], name=op.f("fk_spc_passage_section_id_spc_section")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_spc_passage")),
        sa.UniqueConstraint("section_id", "rank", name="rank"),
        schema="reg",
    )
    op.create_index(op.f("ix_reg_spc_passage_section_id"), "spc_passage", ["section_id"], schema="reg")
    op.execute("CREATE INDEX ix_spc_passage_tsv ON reg.spc_passage USING gin (tsv)")
    op.execute("CREATE INDEX ix_spc_passage_embedding ON reg.spc_passage USING hnsw (embedding vector_cosine_ops)")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("spc_passage", schema="reg")
    op.drop_table("spc_section", schema="reg")
