"""drop legacy feature-titled session rows

Sessions created by run_summarize / run_quiz / run_flashcards /
run_study_pack / run_learning_pack accumulated in the `sessions` table
with synthetic titles ("Summarize", "Quiz", "Flashcards", "Study Pack",
"Learning Pack"). These were never real conversations — the studio
panel polluted the user's chat history. The artifact persistence layer
(notebook_artifacts) now owns the per-notebook cached results, so the
feature endpoints no longer create session rows. This migration cleans
up the existing pollution.

Cascades: each deleted session takes its messages and agent_runs rows
with it via ON DELETE CASCADE — those messages were always empty (the
feature endpoints never inserted any), and the agent_runs were audit
records that have no remaining UI consumer.

Revision ID: a5e29c1d83f4
Revises: f8b24d9c1a36
Create Date: 2026-05-19 11:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a5e29c1d83f4"
down_revision: str | Sequence[str] | None = "f8b24d9c1a36"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_LEGACY_TITLES = (
    "Summarize",
    "Quiz",
    "Flashcards",
    "Study Pack",
    "Learning Pack",
)


def upgrade() -> None:
    # Parameterised IN clause — bind list literal so values are
    # quoted/escaped by the driver, not by string interpolation.
    op.execute(
        sa.text("DELETE FROM sessions WHERE title IN :titles").bindparams(
            sa.bindparam("titles", _LEGACY_TITLES, expanding=True)
        )
    )


def downgrade() -> None:
    # Irreversible: the deleted rows had no real chat content, so we
    # can't reconstruct them. No-op the downgrade rather than fail.
    pass
