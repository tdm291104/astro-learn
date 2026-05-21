"""add token_usage_events table

Revision ID: d3c64a8b91e5
Revises: a5e29c1d83f4
Create Date: 2026-05-19 14:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3c64a8b91e5"
down_revision: str | Sequence[str] | None = "a5e29c1d83f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "token_usage_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column(
            "prompt_tokens", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column(
            "completion_tokens",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "total_tokens", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_token_usage_user_created",
        "token_usage_events",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_token_usage_user_created", table_name="token_usage_events")
    op.drop_table("token_usage_events")
