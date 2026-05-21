"""add share_settings to notebooks

Revision ID: 4d1e8b3a6c19
Revises: 3c8a2d9e1f47
Create Date: 2026-05-12 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '4d1e8b3a6c19'
down_revision: str | Sequence[str] | None = '3c8a2d9e1f47'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NOT NULL with a server-side default of {"show_filenames": false} —
    # all existing rows pick up the safe default automatically. Owners
    # who actively want filenames visible call PATCH
    # /notebooks/{id}/share/settings to flip the toggle.
    op.add_column(
        'notebooks',
        sa.Column(
            'share_settings',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{\"show_filenames\": false}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column('notebooks', 'share_settings')
