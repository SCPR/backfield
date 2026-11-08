"""Pgvector column type with SQLite-safe fallback for tests."""

from __future__ import annotations

import os

from sqlalchemy.types import Text, TypeDecorator

EMBEDDING_DIMENSIONS_ENV = "BACKFIELD_EMBEDDING_DIMENSIONS"
_FALLBACK_EMBEDDING_DIMENSIONS = 1536

# Every pgvector embedding column, as (table, column).
EMBEDDING_VECTOR_COLUMNS: tuple[tuple[str, str], ...] = (
    ("substrate_article_embedding", "embedding"),
    ("substrate_image_embedding", "embedding"),
    ("substrate_person_semantic_document", "embedding"),
    ("substrate_location_semantic_document", "embedding"),
    ("substrate_organization_semantic_document", "embedding"),
)


def configured_embedding_dimensions() -> int:
    """Vector size for every embedding column (``BACKFIELD_EMBEDDING_DIMENSIONS``, default 1536).

    Must match the deployment's embedding model, e.g. 1536 for OpenAI text-embedding-3-small or
    1024 for Amazon Titan Text Embeddings V2. Resize existing columns with
    ``backfield set-embedding-dimensions``.
    """
    raw = (os.environ.get(EMBEDDING_DIMENSIONS_ENV) or "").strip()
    if not raw:
        return _FALLBACK_EMBEDDING_DIMENSIONS
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{EMBEDDING_DIMENSIONS_ENV} must be an integer, got {raw!r}") from exc
    if not 1 <= value <= 16000:
        raise ValueError(f"{EMBEDDING_DIMENSIONS_ENV} must be between 1 and 16000, got {value}")
    return value


DEFAULT_SEMANTIC_EMBEDDING_DIMENSIONS = configured_embedding_dimensions()


class _PostgresVector(TypeDecorator):
    """Render pgvector ``vector(n)`` on Postgres and plain text elsewhere."""

    impl = Text
    cache_ok = True

    def __init__(self, dimensions: int = DEFAULT_SEMANTIC_EMBEDDING_DIMENSIONS) -> None:
        self.dimensions = int(dimensions)
        super().__init__()

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector

            return dialect.type_descriptor(Vector(self.dimensions))
        return dialect.type_descriptor(Text())
