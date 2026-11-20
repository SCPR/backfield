"""Add content_type on substrate articles (article, show_segment).

Existing rows become ``article`` through the server default; Postgres adds a column with a
constant default without rewriting the table.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "085_article_content_type"
down_revision: str | None = "084_article_passage"
branch_labels: Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "substrate_article",
        sa.Column("content_type", sa.Text(), nullable=False, server_default="article"),
    )
    op.create_index(
        "idx_substrate_article_project_content_type",
        "substrate_article",
        ["project_id", "content_type"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_substrate_article_project_content_type",
        table_name="substrate_article",
    )
    op.drop_column("substrate_article", "content_type")
