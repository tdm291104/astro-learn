"""add interpretation to analyses

Revision ID: b18f3d7c2a9e
Revises: a4f9c2e8b71d
Create Date: 2026-05-18 00:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b18f3d7c2a9e'
down_revision: str | Sequence[str] | None = 'a4f9c2e8b71d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable so the column rollout is online-safe and so older analyses (run
    # before FitsAnalystAgent ships in Increment D) keep working — the FE
    # renderer treats NULL as "no interpretation, fall back to raw renderers".
    op.add_column(
        'analyses',
        sa.Column(
            'interpretation',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column('analyses', 'interpretation')
