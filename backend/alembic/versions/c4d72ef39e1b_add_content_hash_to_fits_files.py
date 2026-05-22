"""add content_hash to fits_files for upload dedup

Revision ID: c4d72ef39e1b
Revises: e9f31b7d4c08
Create Date: 2026-05-22 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4d72ef39e1b"
down_revision: str | Sequence[str] | None = "e9f31b7d4c08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable: existing rows take NULL until a backfill script computes the
    # SHA-256 from storage_path. New uploads write the hash before insert.
    op.add_column(
        "fits_files",
        sa.Column("content_hash", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "ix_fits_files_owner_hash",
        "fits_files",
        ["owner_id", "content_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_fits_files_owner_hash", table_name="fits_files")
    op.drop_column("fits_files", "content_hash")
