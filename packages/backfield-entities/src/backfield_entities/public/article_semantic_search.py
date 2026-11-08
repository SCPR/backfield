"""Semantic article search over article embeddings or article passages.

Two indexes can back it: one vector per article (``substrate_article_embedding``, written by
the Embed Text node) or many passage vectors per article (``substrate_article_passage``,
written by the passage indexer). Passage search ranks each article by its best-matching
passage and returns the matching passages with the article.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

from backfield_db import SubstrateArticle, SubstrateArticleEmbedding, SubstrateArticlePassage
from backfield_db.pgvector import _PostgresVector
from pydantic import BaseModel
from sqlalchemy import Float, and_, literal, or_, text
from sqlmodel import Session, col, select

from backfield_entities.ingest.semantic_indexing.search import (
    _coerce_embedding_vector,
    cosine_similarity,
)
from backfield_entities.public.articles import (
    ArticleMetaClause,
    PublicArticleOut,
    _apply_public_article_list_filters,
    _article_to_public_out,
    _meta_rows_for_articles,
)

# Passage candidates pulled from the vector index before grouping by article. Articles are
# ranked within this pool, so ``total`` counts matching articles found in it.
MIN_PASSAGE_CANDIDATES = 200
MAX_PASSAGE_CANDIDATES = 2000
HNSW_EF_SEARCH = 200


class PublicArticlePassageHitOut(BaseModel):
    passage_index: int
    text: str
    score: float


class PublicArticleSemanticSearchItemOut(PublicArticleOut):
    score: float
    passages: list[PublicArticlePassageHitOut] | None = None


@dataclass(frozen=True)
class PublicArticleSemanticSearchParams:
    meta_type: str | None = None
    meta_category: str | None = None
    exclude_meta_type: str | None = None
    exclude_meta_category: str | None = None
    meta_clauses: tuple[ArticleMetaClause, ...] = ()
    pub_date_from: date | None = None
    pub_date_to: date | None = None
    limit: int = 25
    offset: int = 0


def _embedding_rows_for_project(
    session: Session,
    *,
    project_id: int,
    embedding_model_config_id: str,
    embedding_provider_model_id: str,
    params: PublicArticleSemanticSearchParams,
) -> list[tuple[SubstrateArticle, SubstrateArticleEmbedding]]:
    stmt = (
        select(SubstrateArticle, SubstrateArticleEmbedding)
        .join(
            SubstrateArticleEmbedding,
            col(SubstrateArticleEmbedding.article_id) == col(SubstrateArticle.id),
        )
        .where(
            SubstrateArticle.project_id == project_id,
            SubstrateArticle.deleted == False,  # noqa: E712
            col(SubstrateArticleEmbedding.embedding).isnot(None),
            or_(
                SubstrateArticleEmbedding.embedding_ai_model_config_id
                == embedding_model_config_id,
                and_(
                    col(SubstrateArticleEmbedding.embedding_ai_model_config_id).is_(None),
                    SubstrateArticleEmbedding.embedding_model == embedding_provider_model_id,
                ),
            ),
        )
    )
    stmt = _apply_public_article_list_filters(
        stmt,
        meta_type=params.meta_type,
        meta_category=params.meta_category,
        exclude_meta_type=params.exclude_meta_type,
        exclude_meta_category=params.exclude_meta_category,
        meta_clauses=params.meta_clauses,
        pub_date_from=params.pub_date_from,
        pub_date_to=params.pub_date_to,
    )
    return list(session.exec(stmt).all())


def _coerce_sqlite_embedding(raw: object | None) -> list[float] | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return _coerce_embedding_vector(parsed)
    return _coerce_embedding_vector(raw)


def search_public_articles_semantic(
    session: Session,
    *,
    project_id: int,
    query_vector: list[float],
    embedding_model_config_id: str,
    embedding_provider_model_id: str,
    params: PublicArticleSemanticSearchParams,
) -> tuple[list[PublicArticleSemanticSearchItemOut], int]:
    """Rank project articles by cosine similarity when an embedding row exists."""
    rows = _embedding_rows_for_project(
        session,
        project_id=project_id,
        embedding_model_config_id=embedding_model_config_id,
        embedding_provider_model_id=embedding_provider_model_id,
        params=params,
    )

    ranked: list[tuple[float, SubstrateArticle]] = []
    for article, embedding_row in rows:
        vector = _coerce_embedding_vector(getattr(embedding_row, "embedding", None))
        if vector is None:
            vector = _coerce_sqlite_embedding(getattr(embedding_row, "embedding", None))
        if vector is None or len(vector) != len(query_vector):
            continue
        score = cosine_similarity(query_vector, vector)
        ranked.append((score, article))

    ranked.sort(
        key=lambda item: (
            -item[0],
            item[1].pub_date.isoformat() if item[1].pub_date is not None else "",
            -int(item[1].id or 0),
        )
    )
    total = len(ranked)
    page = ranked[params.offset : params.offset + params.limit]

    article_ids = [int(article.id) for _, article in page if article.id is not None]
    meta_by_id = _meta_rows_for_articles(session, article_ids)

    items = [
        PublicArticleSemanticSearchItemOut(
            **_article_to_public_out(
                article,
                metadata=meta_by_id.get(int(article.id), []),  # type: ignore[arg-type]
            ).model_dump(),
            score=score,
        )
        for score, article in page
    ]
    return items, total


def _passage_filters(
    stmt,
    *,
    project_id: int,
    embedding_model_config_id: str,
    params: PublicArticleSemanticSearchParams,
):
    stmt = stmt.join(
        SubstrateArticlePassage,
        col(SubstrateArticlePassage.article_id) == col(SubstrateArticle.id),
    ).where(
        SubstrateArticlePassage.project_id == project_id,
        SubstrateArticle.project_id == project_id,
        SubstrateArticle.deleted == False,  # noqa: E712
        SubstrateArticlePassage.embedding_ai_model_config_id == embedding_model_config_id,
        col(SubstrateArticlePassage.embedding).isnot(None),
    )
    return _apply_public_article_list_filters(
        stmt,
        meta_type=params.meta_type,
        meta_category=params.meta_category,
        exclude_meta_type=params.exclude_meta_type,
        exclude_meta_category=params.exclude_meta_category,
        meta_clauses=params.meta_clauses,
        pub_date_from=params.pub_date_from,
        pub_date_to=params.pub_date_to,
    )


def _passage_candidates(
    session: Session,
    *,
    project_id: int,
    query_vector: list[float],
    embedding_model_config_id: str,
    params: PublicArticleSemanticSearchParams,
    candidate_limit: int,
) -> list[tuple[SubstrateArticle, int, str, float]]:
    """Closest passages as ``(article, passage_index, passage_text, cosine_similarity)``."""
    bind = session.get_bind()
    if bind.dialect.name == "postgresql":
        query_param = literal(query_vector, type_=_PostgresVector(len(query_vector)))
        distance = col(SubstrateArticlePassage.embedding).op("<=>", return_type=Float)(
            query_param
        )
        stmt = select(
            SubstrateArticle,
            SubstrateArticlePassage.passage_index,
            SubstrateArticlePassage.passage_text,
            distance.label("distance"),
        )
        stmt = _passage_filters(
            stmt,
            project_id=project_id,
            embedding_model_config_id=embedding_model_config_id,
            params=params,
        )
        stmt = stmt.order_by(distance).limit(candidate_limit)
        # Keep scanning the HNSW index until enough rows survive the article filters
        # (pgvector >= 0.8); results are re-sorted after grouping.
        session.exec(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))  # type: ignore[call-overload]
        session.exec(text(f"SET LOCAL hnsw.ef_search = {HNSW_EF_SEARCH}"))  # type: ignore[call-overload]
        return [
            (article, int(index), str(passage), 1.0 - float(dist))
            for article, index, passage, dist in session.exec(stmt).all()
        ]

    # SQLite (tests): vectors are stored as JSON text; rank in Python.
    stmt = select(
        SubstrateArticle,
        SubstrateArticlePassage.passage_index,
        SubstrateArticlePassage.passage_text,
        SubstrateArticlePassage.embedding,
    )
    stmt = _passage_filters(
        stmt,
        project_id=project_id,
        embedding_model_config_id=embedding_model_config_id,
        params=params,
    )
    scored: list[tuple[SubstrateArticle, int, str, float]] = []
    for article, index, passage, raw in session.exec(stmt).all():
        vector = _coerce_sqlite_embedding(raw)
        if vector is None or len(vector) != len(query_vector):
            continue
        scored.append((article, int(index), str(passage), cosine_similarity(query_vector, vector)))
    scored.sort(key=lambda row: -row[3])
    return scored[:candidate_limit]


def search_public_articles_by_passages(
    session: Session,
    *,
    project_id: int,
    query_vector: list[float],
    embedding_model_config_id: str,
    params: PublicArticleSemanticSearchParams,
    passages_per_article: int = 3,
) -> tuple[list[PublicArticleSemanticSearchItemOut], int]:
    """Rank articles by their best-matching passage; return the top passages with each."""
    wanted = (params.offset + params.limit) * passages_per_article * 4
    candidate_limit = max(MIN_PASSAGE_CANDIDATES, min(MAX_PASSAGE_CANDIDATES, wanted))
    candidates = _passage_candidates(
        session,
        project_id=project_id,
        query_vector=query_vector,
        embedding_model_config_id=embedding_model_config_id,
        params=params,
        candidate_limit=candidate_limit,
    )

    by_article: dict[int, tuple[SubstrateArticle, list[PublicArticlePassageHitOut]]] = {}
    for article, index, passage, score in candidates:
        entry = by_article.setdefault(int(article.id), (article, []))  # type: ignore[arg-type]
        entry[1].append(PublicArticlePassageHitOut(passage_index=index, text=passage, score=score))

    ranked: list[tuple[float, SubstrateArticle, list[PublicArticlePassageHitOut]]] = []
    for article, hits in by_article.values():
        hits.sort(key=lambda h: -h.score)
        ranked.append((hits[0].score, article, hits[:passages_per_article]))
    ranked.sort(key=lambda item: (-item[0], -int(item[1].id or 0)))

    total = len(ranked)
    page = ranked[params.offset : params.offset + params.limit]
    meta_by_id = _meta_rows_for_articles(session, [int(a.id) for _, a, _ in page])  # type: ignore[arg-type]
    items = [
        PublicArticleSemanticSearchItemOut(
            **_article_to_public_out(
                article,
                metadata=meta_by_id.get(int(article.id), []),  # type: ignore[arg-type]
            ).model_dump(),
            score=score,
            passages=hits,
        )
        for score, article, hits in page
    ]
    return items, total
