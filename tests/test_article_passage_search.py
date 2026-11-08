"""Voyage context embeddings, article passage indexing, and passage-ranked article search."""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from backfield_ai import article_passages
from backfield_ai.embeddings import EmbeddingModelAuth, embed_texts_sync
from backfield_ai.voyage_context import (
    ContextChunk,
    ContextEmbedResponse,
    VoyageContextError,
    contextualized_embed,
    document_batches,
    is_voyage_context_model,
    voyage_context_model_name,
)
from backfield_db import (
    BackfieldOrganization,
    BackfieldProject,
    SubstrateArticle,
    SubstrateArticlePassage,
)
from backfield_db.pgvector import EMBEDDING_DIMENSIONS_ENV
from backfield_entities.public.article_semantic_search import (
    PublicArticleSemanticSearchParams,
    search_public_articles_by_passages,
)
from sqlmodel import Session, SQLModel, create_engine, select

from tests.project_helpers import project_ownership_fields

CONFIG_ID = "cfg-voyage-context"
LM = "voyage/voyage-context-4"


def _response(documents: list[list[tuple[str | None, list[float]]]], tokens: int = 10) -> dict:
    return {
        "object": "list",
        "data": [
            {
                "object": "list",
                "index": d,
                "data": [
                    {"object": "embedding", "index": c, "embedding": vec, **({"text": t} if t else {})}
                    for c, (t, vec) in enumerate(chunks)
                ],
            }
            for d, chunks in enumerate(documents)
        ],
        "model": "voyage-context-4",
        "usage": {"total_tokens": tokens},
    }


def test_context_model_detection() -> None:
    assert voyage_context_model_name(LM) == "voyage-context-4"
    assert is_voyage_context_model("voyage/voyage-context-3")
    assert not is_voyage_context_model("voyage/voyage-4-large")
    assert not is_voyage_context_model("bedrock/amazon.titan-embed-text-v2:0")


def test_auto_chunking_request_and_chunk_text() -> None:
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200, json=_response([[("Para one.", [1.0, 0.0]), ("Para two.", [0.0, 1.0])]], 42)
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        resp = contextualized_embed(
            api_key="k",
            model="voyage-context-4",
            inputs=["Para one. Para two."],
            input_type="document",
            output_dimension=1024,
            auto_chunk=True,
            chunk_size=512,
            client=client,
        )
    assert seen["url"] == "https://api.voyageai.com/v1/contextualizedembeddings"
    assert seen["auth"] == "Bearer k"
    assert seen["body"] == {
        "inputs": ["Para one. Para two."],
        "model": "voyage-context-4",
        "input_type": "document",
        "output_dimension": 1024,
        "enable_auto_chunking": True,
        "chunk_size": 512,
    }
    assert [c.text for c in resp.documents[0]] == ["Para one.", "Para two."]
    assert resp.total_tokens == 42


def test_auto_chunking_requires_document_input_type() -> None:
    with pytest.raises(VoyageContextError):
        contextualized_embed(
            api_key="k", model="voyage-context-4", inputs=["x"], input_type="query", auto_chunk=True
        )


def test_retries_rate_limits_then_fails_on_client_errors() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, text="slow down")
        return httpx.Response(200, json=_response([[(None, [0.5, 0.5])]]))

    with (
        patch("backfield_ai.voyage_context.time.sleep"),
        httpx.Client(transport=httpx.MockTransport(handler)) as client,
    ):
        resp = contextualized_embed(
            api_key="k", model="voyage-context-4", inputs=[["q"]], input_type="query", client=client
        )
    assert calls["n"] == 2
    assert resp.documents[0][0].vector == [0.5, 0.5]

    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(401))) as client:
        with pytest.raises(VoyageContextError, match="HTTP 401"):
            contextualized_embed(
                api_key="bad", model="voyage-context-4", inputs=[["q"]], input_type="query",
                client=client,
            )


def test_document_batches_respect_token_budget() -> None:
    docs = ["a" * 300, "b" * 300, "c" * 300]  # ~100 estimated tokens each
    assert list(document_batches(docs, token_budget=250)) == [[0, 1], [2]]
    assert list(document_batches(docs, token_budget=10_000, max_inputs=2)) == [[0, 1], [2]]


def test_embed_texts_sync_routes_context_models_to_voyage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(EMBEDDING_DIMENSIONS_ENV, "2")
    fake = ContextEmbedResponse(
        documents=[[ContextChunk(text=None, vector=[0.6, 0.8])]], total_tokens=1000, latency_ms=5
    )
    with (
        patch("backfield_ai.embeddings.contextualized_embed", return_value=fake) as call,
        patch("backfield_ai.embeddings.litellm.embedding") as litellm_call,
    ):
        result = embed_texts_sync(
            litellm_model=LM, texts=["heat wave"], api_key="k", input_type="query",
            track_attempt=False,
        )
    litellm_call.assert_not_called()
    kwargs = call.call_args.kwargs
    assert kwargs["inputs"] == [["heat wave"]]
    assert kwargs["input_type"] == "query"
    assert kwargs["output_dimension"] == 2
    assert result.items[0].vector == [0.6, 0.8]
    assert result.total_tokens == 1000
    assert result.estimated_cost is not None and result.estimated_cost > 0


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _project_with_articles(session: Session) -> tuple[int, list[int]]:
    org = BackfieldOrganization(name="Org", slug="org-passages")
    session.add(org)
    session.commit()
    session.refresh(org)
    proj = BackfieldProject(
        **project_ownership_fields(session, int(org.id)),
        name="News",
        slug="news-passages",
        organization_id=int(org.id),  # type: ignore[arg-type]
    )
    session.add(proj)
    session.commit()
    session.refresh(proj)
    articles = [
        SubstrateArticle(
            project_id=int(proj.id),  # type: ignore[arg-type]
            headline="Cooling centers open",
            text="Libraries stay open late. Pools extend hours.",
            pub_date=date(2026, 7, 1),
        ),
        SubstrateArticle(
            project_id=int(proj.id),  # type: ignore[arg-type]
            headline="Council budget",
            text="The council passed a budget.",
            pub_date=date(2026, 6, 1),
        ),
    ]
    session.add_all(articles)
    session.commit()
    return int(proj.id), [int(a.id) for a in articles]  # type: ignore[arg-type]


def _auth() -> EmbeddingModelAuth:
    return EmbeddingModelAuth(
        litellm_model=LM, api_key="k", api_base=None, model_config_id=CONFIG_ID, config_json=None
    )


def _fake_embed(**kwargs) -> ContextEmbedResponse:
    docs = []
    for text in kwargs["inputs"]:
        if text.startswith("Cooling"):
            docs.append(
                [
                    ContextChunk("Libraries stay open late.", [1.0, 0.0]),
                    ContextChunk("Pools extend hours.", [0.8, 0.6]),
                ]
            )
        else:
            docs.append([ContextChunk("The council passed a budget.", [0.0, 1.0])])
    return ContextEmbedResponse(documents=docs, total_tokens=30, latency_ms=1)


def _patched_indexer():
    return (
        patch.object(
            article_passages,
            "resolve_article_passage_embedding_model_config_id",
            return_value=CONFIG_ID,
        ),
        patch.object(
            article_passages, "resolve_embedding_auth_for_model_config", return_value=_auth()
        ),
        patch.object(article_passages, "persist_llm_attempt"),
    )


def test_index_then_search_ranks_by_best_passage(session: Session) -> None:
    project_id, (cooling_id, budget_id) = _project_with_articles(session)
    resolve, auth, attempt = _patched_indexer()
    with resolve, auth, attempt, patch.object(
        article_passages, "contextualized_embed", side_effect=_fake_embed
    ) as embed:
        summary = article_passages.index_article_passages(session, project_id=project_id)
        session.commit()
        assert summary.status == "succeeded"
        assert (summary.articles_indexed, summary.passages_written) == (2, 3)
        assert embed.call_args.kwargs["auto_chunk"] is True
        assert embed.call_args.kwargs["input_type"] == "document"

        # Unchanged text is skipped on the next run.
        again = article_passages.index_article_passages(session, project_id=project_id)
        assert (again.articles_indexed, again.articles_unchanged) == (0, 2)
        assert embed.call_count == 1

    items, total = search_public_articles_by_passages(
        session,
        project_id=project_id,
        query_vector=[1.0, 0.1],
        embedding_model_config_id=CONFIG_ID,
        params=PublicArticleSemanticSearchParams(limit=10),
    )
    assert total == 2
    assert [i.id for i in items] == [cooling_id, budget_id]
    assert [p.text for p in items[0].passages or []] == [
        "Libraries stay open late.",
        "Pools extend hours.",
    ]
    assert items[0].score == pytest.approx(items[0].passages[0].score)  # type: ignore[index]

    dated = search_public_articles_by_passages(
        session,
        project_id=project_id,
        query_vector=[1.0, 0.1],
        embedding_model_config_id=CONFIG_ID,
        params=PublicArticleSemanticSearchParams(pub_date_to=date(2026, 6, 30)),
    )
    assert [i.id for i in dated[0]] == [budget_id]


def test_deleted_articles_lose_passages_and_edits_reindex(session: Session) -> None:
    project_id, (cooling_id, budget_id) = _project_with_articles(session)
    resolve, auth, attempt = _patched_indexer()
    with resolve, auth, attempt, patch.object(
        article_passages, "contextualized_embed", side_effect=_fake_embed
    ) as embed:
        article_passages.index_article_passages(session, project_id=project_id)
        budget = session.get(SubstrateArticle, budget_id)
        budget.deleted = True  # type: ignore[union-attr]
        cooling = session.get(SubstrateArticle, cooling_id)
        cooling.text = "Libraries stay open late. Pools extend hours. Buses are free."  # type: ignore[union-attr]
        session.commit()
        summary = article_passages.index_article_passages(session, project_id=project_id)
        assert summary.articles_indexed == 1
        assert embed.call_args.kwargs["inputs"][0].startswith("Cooling centers open")
    ids = session.exec(select(SubstrateArticlePassage.article_id)).all()
    assert set(ids) == {cooling_id}


def test_failed_batch_reports_partial_without_writing(session: Session) -> None:
    project_id, _ = _project_with_articles(session)
    resolve, auth, attempt = _patched_indexer()
    with resolve, auth, attempt, patch.object(
        article_passages, "contextualized_embed", side_effect=VoyageContextError("HTTP 500")
    ):
        summary = article_passages.index_article_passages(session, project_id=project_id)
    assert summary.status == "failed"
    assert summary.articles_failed == 2
    assert session.exec(select(SubstrateArticlePassage)).all() == []


def test_not_configured_is_a_no_op(session: Session) -> None:
    project_id, _ = _project_with_articles(session)
    with patch.object(
        article_passages, "resolve_article_passage_embedding_model_config_id", return_value=None
    ):
        summary = article_passages.index_article_passages(session, project_id=project_id)
    assert summary.status == "not_configured"


def test_non_context_model_is_rejected(session: Session) -> None:
    project_id, _ = _project_with_articles(session)
    titan = SimpleNamespace(**{**_auth().__dict__, "litellm_model": "bedrock/amazon.titan"})
    with (
        patch.object(
            article_passages,
            "resolve_article_passage_embedding_model_config_id",
            return_value=CONFIG_ID,
        ),
        patch.object(article_passages, "resolve_embedding_auth_for_model_config", return_value=titan),
        pytest.raises(ValueError, match="Voyage context model"),
    ):
        article_passages.index_article_passages(session, project_id=project_id)
