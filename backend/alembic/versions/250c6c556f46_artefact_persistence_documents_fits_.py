"""artefact persistence (documents, fits_files, analyses, reports)

Revision ID: 250c6c556f46
Revises: 7521436aa891
Create Date: 2026-05-07 00:37:44.347756

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '250c6c556f46'
down_revision: str | Sequence[str] | None = '7521436aa891'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('fits_files',
    sa.Column('owner_id', sa.Uuid(), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('content_type', sa.String(length=128), nullable=True),
    sa.Column('size_bytes', sa.BigInteger(), nullable=False),
    sa.Column('storage_path', sa.String(length=512), nullable=False),
    sa.Column('hdu_count', sa.Integer(), nullable=False),
    sa.Column('hdus', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('primary_headers', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_fits_files_owner_id'), 'fits_files', ['owner_id'], unique=False)
    op.create_table('documents',
    sa.Column('notebook_id', sa.Uuid(), nullable=False),
    sa.Column('owner_id', sa.Uuid(), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('content_type', sa.String(length=128), nullable=True),
    sa.Column('size_bytes', sa.BigInteger(), nullable=False),
    sa.Column('storage_path', sa.String(length=512), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('indexed_chunks', sa.Integer(), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('extra', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['notebook_id'], ['notebooks.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_documents_notebook_id'), 'documents', ['notebook_id'], unique=False)
    op.create_index(op.f('ix_documents_owner_id'), 'documents', ['owner_id'], unique=False)
    op.create_table('analyses',
    sa.Column('owner_id', sa.Uuid(), nullable=False),
    sa.Column('file_id', sa.Uuid(), nullable=False),
    sa.Column('agent_run_id', sa.Uuid(), nullable=True),
    sa.Column('analysis_type', sa.String(length=32), nullable=False),
    sa.Column('hdu_index', sa.Integer(), nullable=False),
    sa.Column('params', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('status', sa.String(length=32), nullable=False),
    sa.Column('results', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('artifacts', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['agent_run_id'], ['agent_runs.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['file_id'], ['fits_files.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_analyses_agent_run_id'), 'analyses', ['agent_run_id'], unique=False)
    op.create_index(op.f('ix_analyses_file_id'), 'analyses', ['file_id'], unique=False)
    op.create_index(op.f('ix_analyses_owner_id'), 'analyses', ['owner_id'], unique=False)
    op.create_table('reports',
    sa.Column('owner_id', sa.Uuid(), nullable=False),
    sa.Column('analysis_id', sa.Uuid(), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('format', sa.String(length=16), nullable=False),
    sa.Column('storage_path', sa.String(length=512), nullable=False),
    sa.Column('include_plots', sa.Boolean(), nullable=False),
    sa.Column('generated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['analysis_id'], ['analyses.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_reports_analysis_id'), 'reports', ['analysis_id'], unique=False)
    op.create_index(op.f('ix_reports_owner_id'), 'reports', ['owner_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_reports_owner_id'), table_name='reports')
    op.drop_index(op.f('ix_reports_analysis_id'), table_name='reports')
    op.drop_table('reports')
    op.drop_index(op.f('ix_analyses_owner_id'), table_name='analyses')
    op.drop_index(op.f('ix_analyses_file_id'), table_name='analyses')
    op.drop_index(op.f('ix_analyses_agent_run_id'), table_name='analyses')
    op.drop_table('analyses')
    op.drop_index(op.f('ix_documents_owner_id'), table_name='documents')
    op.drop_index(op.f('ix_documents_notebook_id'), table_name='documents')
    op.drop_table('documents')
    op.drop_index(op.f('ix_fits_files_owner_id'), table_name='fits_files')
    op.drop_table('fits_files')
