"""add share_token to notebooks

Revision ID: 3c8a2d9e1f47
Revises: bf6297faaa8b
Create Date: 2026-05-11 19:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '3c8a2d9e1f47'
down_revision: str | Sequence[str] | None = 'bf6297faaa8b'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable so existing rows default to "no public link". UNIQUE
    # enforced at the column level — `secrets.token_urlsafe` collisions
    # are vanishingly unlikely, but a constraint here means the rare
    # collision raises an IntegrityError instead of silently merging
    # two notebooks into one share URL.
    op.add_column(
        'notebooks',
        sa.Column('share_token', sa.String(length=64), nullable=True),
    )
    op.create_unique_constraint(
        'uq_notebooks_share_token', 'notebooks', ['share_token'],
    )
    op.create_index(
        'ix_notebooks_share_token', 'notebooks', ['share_token'], unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_notebooks_share_token', table_name='notebooks')
    op.drop_constraint('uq_notebooks_share_token', 'notebooks', type_='unique')
    op.drop_column('notebooks', 'share_token')
