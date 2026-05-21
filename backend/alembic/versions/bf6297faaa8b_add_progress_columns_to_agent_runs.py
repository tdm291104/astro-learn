"""add progress columns to agent_runs

Revision ID: bf6297faaa8b
Revises: fc27006e2ca2
Create Date: 2026-05-11 18:02:50.282178

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'bf6297faaa8b'
down_revision: str | Sequence[str] | None = 'fc27006e2ca2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # `step_count` is NOT NULL — `server_default="0"` backfills existing
    # rows during the ALTER so the migration doesn't fail on populated
    # tables. `current_step` + `progress` are nullable so no backfill
    # value is needed for those.
    op.add_column(
        'agent_runs',
        sa.Column(
            'step_count',
            sa.Integer(),
            nullable=False,
            server_default=sa.text('0'),
        ),
    )
    op.add_column('agent_runs', sa.Column('current_step', sa.String(length=128), nullable=True))
    op.add_column('agent_runs', sa.Column('progress', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('agent_runs', 'progress')
    op.drop_column('agent_runs', 'current_step')
    op.drop_column('agent_runs', 'step_count')
