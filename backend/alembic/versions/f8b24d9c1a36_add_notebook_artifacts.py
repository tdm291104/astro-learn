"""add notebook_artifacts table

Revision ID: f8b24d9c1a36
Revises: e7a13c4f9b22
Create Date: 2026-05-19 09:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f8b24d9c1a36"
down_revision: str | Sequence[str] | None = "e7a13c4f9b22"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notebook_artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "notebook_id",
            sa.Uuid(),
            sa.ForeignKey("notebooks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column(
            "params",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "notebook_id", "kind", name="uq_notebook_artifact_kind"
        ),
    )
    op.create_index(
        op.f("ix_notebook_artifacts_notebook_id"),
        "notebook_artifacts",
        ["notebook_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_notebook_artifacts_notebook_id"),
        table_name="notebook_artifacts",
    )
    op.drop_table("notebook_artifacts")
