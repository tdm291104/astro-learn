"""add catalog_cache table

Revision ID: fc27006e2ca2
Revises: 250c6c556f46
Create Date: 2026-05-11 12:10:38.491049

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'fc27006e2ca2'
down_revision: str | Sequence[str] | None = '250c6c556f46'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('catalog_cache',
    sa.Column('query_norm', sa.String(length=256), nullable=False),
    sa.Column('source', sa.String(length=16), nullable=False),
    sa.Column('results', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('result_count', sa.Integer(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('extra', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('query_norm', 'source', name='uq_catalog_cache_query_source')
    )
    op.create_index('ix_catalog_cache_expires_at', 'catalog_cache', ['expires_at'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_catalog_cache_expires_at', table_name='catalog_cache')
    op.drop_table('catalog_cache')
