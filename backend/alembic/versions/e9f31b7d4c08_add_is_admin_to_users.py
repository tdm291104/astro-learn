"""add is_admin to users

Revision ID: e9f31b7d4c08
Revises: d3c64a8b91e5
Create Date: 2026-05-19 15:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e9f31b7d4c08"
down_revision: str | Sequence[str] | None = "d3c64a8b91e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default makes the column NOT NULL safe even when the table
    # already has rows; new accounts default to non-admin so existing
    # users keep their old privileges.
    op.add_column(
        "users",
        sa.Column(
            "is_admin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "is_admin")
