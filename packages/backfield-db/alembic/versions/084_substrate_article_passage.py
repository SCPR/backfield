"""Passage-level article embeddings for article search, with an HNSW cosine index.

The vector size follows ``BACKFIELD_EMBEDDING_DIMENSIONS`` (default 1536) like the other
embedding columns; ``backfield set-embedding-dimensions`` resizes it with them.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "084_article_passage"
down_revision: str | None = "083_article_headline_url_fts"
branch_labels: Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _embedding_column() -> sa.Column:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        from backfield_db.pgvector import configured_embedding_dimensions
        from pgvector.sqlalchemy import Vector

        return sa.Column("embedding", Vector(configured_embedding_dimensions()), nullable=True)
    return sa.Column("embedding", sa.Text(), nullable=True)


def upgrade() -> None:
    op.create_table(
        "substrate_article_passage",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=False),
        sa.Column("passage_index", sa.Integer(), nullable=False),
        sa.Column("passage_text", sa.Text(), nullable=False),
        sa.Column("source_hash", sa.Text(), nullable=False),
        sa.Column("embedding_model", sa.Text(), nullable=False),
        sa.Column("embedding_ai_model_config_id", sa.Text(), nullable=True),
        _embedding_column(),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["backfield_project.id"],
            name="substrate_article_passage_project_id_fkey",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["article_id"],
            ["substrate_article.id"],
            name="substrate_article_passage_article_id_fkey",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="substrate_article_passage_pkey"),
        sa.UniqueConstraint(
            "article_id", "passage_index", name="uq_substrate_article_passage_article_index"
        ),
    )
    op.create_index(
        "ix_substrate_article_passage_project_id", "substrate_article_passage", ["project_id"]
    )
    op.create_index(
        "ix_substrate_article_passage_article_id", "substrate_article_passage", ["article_id"]
    )
    op.create_index(
        "ix_substrate_article_passage_embedding_ai_model_config_id",
        "substrate_article_passage",
        ["embedding_ai_model_config_id"],
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX idx_substrate_article_passage_embedding_hnsw "
            "ON substrate_article_passage USING hnsw (embedding vector_cosine_ops)"
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS idx_substrate_article_passage_embedding_hnsw")
    op.drop_index(
        "ix_substrate_article_passage_embedding_ai_model_config_id",
        table_name="substrate_article_passage",
    )
    op.drop_index("ix_substrate_article_passage_article_id", table_name="substrate_article_passage")
    op.drop_index("ix_substrate_article_passage_project_id", table_name="substrate_article_passage")
    op.drop_table("substrate_article_passage")
