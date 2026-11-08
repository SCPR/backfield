"""Split articles into passages and embed them for passage-level article search.

Uses the project's ``semantic.article_embedding`` model. Voyage context models
(``voyage/voyage-context-*``) receive whole articles with auto-chunking on, so Voyage both
splits the text and embeds each passage with the full article in view. Articles whose text
hasn't changed since they were last indexed with the same model are skipped.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from backfield_db import SubstrateArticle, SubstrateArticlePassage
from backfield_db.pgvector import configured_embedding_dimensions
from sqlmodel import Session, col, delete, select

from backfield_ai.constants import AI_MODEL_KIND_EMBEDDING
from backfield_ai.embeddings import (
    EmbeddingConfigurationError,
    EmbeddingModelAuth,
    resolve_embedding_auth_for_model_config,
)
from backfield_ai.model_resolve import resolve_article_passage_embedding_model_config_id
from backfield_ai.tracking_context import persist_llm_attempt
from backfield_ai.voyage_context import (
    MAX_DOCUMENT_CHARS,
    VoyageContextError,
    contextualized_embed,
    document_batches,
    voyage_context_model_name,
    voyage_token_cost,
)

logger = logging.getLogger(__name__)

# Voyage's default passage size; config_json can override ("chunk_size", "chunk_overlap").
DEFAULT_PASSAGE_TOKENS = 512
CHUNK_SIZE_CONFIG_KEY = "chunk_size"
CHUNK_OVERLAP_CONFIG_KEY = "chunk_overlap"


@dataclass
class PassageIndexSummary:
    status: str  # not_configured | succeeded | partial | failed
    model_config_id: str | None = None
    articles_considered: int = 0
    articles_indexed: int = 0
    articles_unchanged: int = 0
    articles_failed: int = 0
    passages_written: int = 0
    total_tokens: int = 0
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "model_config_id": self.model_config_id,
            "articles_considered": self.articles_considered,
            "articles_indexed": self.articles_indexed,
            "articles_unchanged": self.articles_unchanged,
            "articles_failed": self.articles_failed,
            "passages_written": self.passages_written,
            "total_tokens": self.total_tokens,
            "errors": self.errors[:10],
        }


def article_passage_source_text(article: SubstrateArticle) -> str:
    """Headline then body: the headline gives every passage its story context."""
    headline = (article.headline or "").strip()
    body = (article.text or "").strip()
    text = f"{headline}\n\n{body}" if headline and body else headline or body
    return text[:MAX_DOCUMENT_CHARS]


def _source_hash(text: str, model_config_id: str, chunk_size: int, chunk_overlap: int) -> str:
    key = f"{model_config_id}|{chunk_size}|{chunk_overlap}|{configured_embedding_dimensions()}\n"
    return hashlib.sha256((key + text).encode("utf-8")).hexdigest()


def _chunk_settings(auth: EmbeddingModelAuth) -> tuple[int, int]:
    cfg = auth.config_json or {}
    size = int(cfg.get(CHUNK_SIZE_CONFIG_KEY) or DEFAULT_PASSAGE_TOKENS)
    overlap = int(cfg.get(CHUNK_OVERLAP_CONFIG_KEY) or 0)
    return size, overlap


def _current_hashes(session: Session, article_ids: list[int]) -> dict[int, str | None]:
    """Article id -> its passages' shared hash, or None if any passage lacks a vector."""
    out: dict[int, str | None] = {}
    rows = session.exec(
        select(
            SubstrateArticlePassage.article_id,
            SubstrateArticlePassage.source_hash,
            col(SubstrateArticlePassage.embedding).is_(None),
        ).where(col(SubstrateArticlePassage.article_id).in_(article_ids))
    ).all()
    for article_id, source_hash, missing in rows:
        aid = int(article_id)
        if missing or (aid in out and out[aid] != source_hash):
            out[aid] = None
        elif aid not in out:
            out[aid] = source_hash
    return out


def _record_attempt(
    *,
    auth: EmbeddingModelAuth,
    model: str,
    tokens: int | None,
    latency_ms: int,
    error: str | None,
) -> None:
    cost = voyage_token_cost(auth.litellm_model, tokens)
    persist_llm_attempt(
        provider="voyage",
        provider_model_id=model,
        status="failed" if error else "succeeded",
        attempt_number=1,
        model_config_id=auth.model_config_id,
        model_config_snapshot_json={"provider": "voyage", "provider_model_id": model},
        prompt_tokens=tokens,
        completion_tokens=None,
        total_tokens=tokens,
        estimated_cost=cost,
        currency="USD",
        cost_estimate_incomplete=cost is None,
        latency_ms=latency_ms,
        provider_request_id=None,
        error_type="EmbeddingBatchError" if error else None,
        error_message=(error or None) and error[:2000],
        cost_estimate_source="litellm" if cost is not None else "unavailable",
        model_kind=AI_MODEL_KIND_EMBEDDING,
    )


def index_article_passages(
    session: Session,
    *,
    project_id: int,
    article_ids: list[int] | None = None,
    force: bool = False,
    commit_each_batch: bool = False,
) -> PassageIndexSummary:
    """(Re)index passages for ``article_ids`` (default: every live article in the project).

    Deleted or emptied articles lose their passages. With ``commit_each_batch`` the session
    commits after each embedding request so long backfills keep their progress.
    """
    model_config_id = resolve_article_passage_embedding_model_config_id(session, project_id)
    if model_config_id is None:
        return PassageIndexSummary(status="not_configured")
    summary = PassageIndexSummary(status="succeeded", model_config_id=model_config_id)

    auth = resolve_embedding_auth_for_model_config(
        session, project_id=project_id, model_config_id=model_config_id
    )
    model = voyage_context_model_name(auth.litellm_model)
    if model is None:
        raise EmbeddingConfigurationError(
            "Article passage search needs a Voyage context model (voyage/voyage-context-*); "
            f"{auth.litellm_model!r} can't split articles into passages."
        )
    chunk_size, chunk_overlap = _chunk_settings(auth)

    stmt = select(SubstrateArticle).where(SubstrateArticle.project_id == project_id)
    if article_ids is not None:
        stmt = stmt.where(col(SubstrateArticle.id).in_(article_ids))
    articles = list(session.exec(stmt.order_by(col(SubstrateArticle.id))).all())
    summary.articles_considered = len(articles)

    live: list[tuple[SubstrateArticle, str, str]] = []
    gone: list[int] = []
    for article in articles:
        text = "" if article.deleted else article_passage_source_text(article)
        if not text:
            gone.append(int(article.id))  # type: ignore[arg-type]
            continue
        live.append(
            (article, text, _source_hash(text, model_config_id, chunk_size, chunk_overlap))
        )
    if gone:
        session.exec(
            delete(SubstrateArticlePassage).where(col(SubstrateArticlePassage.article_id).in_(gone))
        )

    existing = _current_hashes(session, [int(a.id) for a, _, _ in live])  # type: ignore[arg-type]
    todo = [
        item for item in live if force or existing.get(int(item[0].id)) != item[2]  # type: ignore[arg-type]
    ]
    summary.articles_unchanged = len(live) - len(todo)

    # SQLite (tests) stores vectors as JSON text, like the other embedding tables.
    as_json = session.get_bind().dialect.name != "postgresql"
    texts = [text for _, text, _ in todo]
    for batch in document_batches(texts):
        t0 = time.perf_counter()
        try:
            resp = contextualized_embed(
                api_key=auth.api_key,
                model=model,
                inputs=[texts[i] for i in batch],
                input_type="document",
                output_dimension=configured_embedding_dimensions(),
                auto_chunk=True,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                api_base=auth.api_base,
            )
        except VoyageContextError as exc:
            msg = str(exc)
            logger.warning("Article passage embedding failed (%d articles): %s", len(batch), msg)
            _record_attempt(
                auth=auth,
                model=model,
                tokens=None,
                latency_ms=int((time.perf_counter() - t0) * 1000),
                error=msg,
            )
            summary.articles_failed += len(batch)
            summary.errors.append(msg)
            continue
        _record_attempt(
            auth=auth, model=model, tokens=resp.total_tokens, latency_ms=resp.latency_ms, error=None
        )
        summary.total_tokens += int(resp.total_tokens or 0)

        for pos, chunks in zip(batch, resp.documents, strict=True):
            article, text, source_hash = todo[pos]
            article_id = int(article.id)  # type: ignore[arg-type]
            session.exec(
                delete(SubstrateArticlePassage).where(
                    SubstrateArticlePassage.article_id == article_id
                )
            )
            for index, chunk in enumerate(chunks):
                session.add(
                    SubstrateArticlePassage(
                        project_id=project_id,
                        article_id=article_id,
                        passage_index=index,
                        # Voyage returns each chunk's text; fall back to the whole text for
                        # a single-chunk article if it ever doesn't.
                        passage_text=chunk.text if chunk.text is not None else text,
                        source_hash=source_hash,
                        embedding_model=auth.litellm_model,
                        embedding_ai_model_config_id=model_config_id,
                        embedding=json.dumps(chunk.vector) if as_json else chunk.vector,
                    )
                )
            summary.articles_indexed += 1
            summary.passages_written += len(chunks)
        session.flush()
        if commit_each_batch:
            session.commit()

    if summary.articles_failed:
        summary.status = "partial" if summary.articles_indexed else "failed"
    return summary
