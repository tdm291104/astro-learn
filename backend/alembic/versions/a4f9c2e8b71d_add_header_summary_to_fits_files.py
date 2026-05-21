"""add header_summary to fits_files

Revision ID: a4f9c2e8b71d
Revises: 4d1e8b3a6c19
Create Date: 2026-05-18 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a4f9c2e8b71d'
down_revision: str | Sequence[str] | None = '4d1e8b3a6c19'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable so the migration is online-safe: existing rows take NULL until
    # scripts/backfill_header_summary.py populates them. New uploads write a
    # value via AstronomyService._summarise_fits().
    op.add_column(
        'fits_files',
        sa.Column(
            'header_summary',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column('fits_files', 'header_summary')
