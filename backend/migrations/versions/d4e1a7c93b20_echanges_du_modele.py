"""Journal du Copilot : invites et réponses brutes du modèle, base des jeux d'entraînement relus.

Revision ID: d4e1a7c93b20
Revises: cf99eb12b8ff
Create Date: 2026-11-24 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d4e1a7c93b20"
down_revision: str | Sequence[str] | None = "cf99eb12b8ff"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "message", sa.Column("exchanges", postgresql.JSONB(astext_type=sa.Text()), nullable=True), schema="copilot"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("message", "exchanges", schema="copilot")
