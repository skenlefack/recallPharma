"""Double authentification (TOTP) gérée par l'application : secret chiffré par compte.

Revision ID: a3f9c1d27e45
Revises: e7b2c4d51a90
Create Date: 2026-11-25 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a3f9c1d27e45"
down_revision: str | Sequence[str] | None = "e7b2c4d51a90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "account_mfa",
        sa.Column("account_id", sa.Text(), nullable=False),
        sa.Column("secret", sa.Text(), nullable=False),
        sa.Column("enabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_step", sa.BigInteger(), nullable=True),
        sa.Column("failed_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["account_id"], ["core.account.id"], name=op.f("fk_account_mfa_account_id_account"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("account_id", name=op.f("pk_account_mfa")),
        schema="core",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("account_mfa", schema="core")
