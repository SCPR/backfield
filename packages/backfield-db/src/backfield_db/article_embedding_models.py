"""Article-level and passage-level embedding rows linked to ``substrate_article``."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text
from sqlmodel import Field, SQLModel, UniqueConstraint, func

from backfield_db.pgvector import DEFAULT_SEMANTIC_EMBEDDING_DIMENSIONS, _PostgresVector


class SubstrateArticleEmbedding(SQLModel, table=True):
    """One embedding vector per article (EmbedText → DBOutput persist)."""

    __tablename__ = "substrate_article_embedding"
    __table_args__ = (
        UniqueConstraint("article_id", name="uq_substrate_article_embedding_article_id"),
    )

    id: int | None = Field(default=None, primary_key=True)
    article_id: int = Field(foreign_key="substrate_article.id", index=True)
    embedded_text: str = Field(sa_column=Column(Text, nullable=False))
    embedding_model: str = Field(sa_column=Column(Text, nullable=False, index=True))
    embedding_dimensions: int
    embedding_ai_model_config_id: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True),
    )
    embedding: object | None = Field(
        default=None,
        sa_column=Column(_PostgresVector(DEFAULT_SEMANTIC_EMBEDDING_DIMENSIONS), nullable=True),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )


class SubstrateArticlePassage(SQLModel, table=True):
    """One embedded passage of an article, for passage-level article search.

    Every passage of an article comes from one embedding call, so all rows for an article
    share ``source_hash`` (the hash of the text that was split) and the model fields.
    Re-indexing replaces the article's rows wholesale.
    """

    __tablename__ = "substrate_article_passage"
    __table_args__ = (
        UniqueConstraint(
            "article_id", "passage_index", name="uq_substrate_article_passage_article_index"
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    project_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("backfield_project.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    article_id: int = Field(
        sa_column=Column(
            Integer,
            ForeignKey("substrate_article.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )
    )
    passage_index: int
    passage_text: str = Field(sa_column=Column(Text, nullable=False))
    source_hash: str = Field(sa_column=Column(Text, nullable=False))
    embedding_model: str = Field(sa_column=Column(Text, nullable=False))
    embedding_ai_model_config_id: str | None = Field(
        default=None,
        sa_column=Column(Text, nullable=True, index=True),
    )
    embedding: object | None = Field(
        default=None,
        sa_column=Column(_PostgresVector(DEFAULT_SEMANTIC_EMBEDDING_DIMENSIONS), nullable=True),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    )
