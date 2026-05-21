"""add mode column to sessions and session_fits_files join table

Revision ID: e7a13c4f9b22
Revises: b18f3d7c2a9e
Create Date: 2026-05-18 09:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7a13c4f9b22"
down_revision: str | Sequence[str] | None = "b18f3d7c2a9e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # `mode` is NOT NULL with a server-side default so existing rows are
    # backfilled to "general" during the ALTER without a separate update.
    op.add_column(
        "sessions",
        sa.Column(
            "mode",
            sa.String(length=32),
            nullable=False,
            server_default="general",
        ),
    )

    op.create_table(
        "session_fits_files",
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "fits_file_id",
            sa.Uuid(),
            sa.ForeignKey("fits_files.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )


def downgrade() -> None:
    op.drop_table("session_fits_files")
    op.drop_column("sessions", "mode")
