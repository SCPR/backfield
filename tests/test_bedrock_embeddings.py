"""Bedrock inference-profile embedding routing and the configurable vector size."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from backfield_ai.embeddings import (
    EmbeddingConfigurationError,
    bedrock_embedding_route,
    embed_texts_sync,
)
from backfield_db.pgvector import (
    EMBEDDING_DIMENSIONS_ENV,
    EMBEDDING_VECTOR_COLUMNS,
    configured_embedding_dimensions,
)

PROFILE = "arn:aws:bedrock:us-west-2:111122223333:application-inference-profile/abc123"
TITAN = {"bedrock_base_model": "amazon.titan-embed-text-v2:0"}


def test_profile_arn_routes_to_base_model_with_model_id() -> None:
    assert bedrock_embedding_route(f"bedrock/{PROFILE}", TITAN) == (
        "bedrock/amazon.titan-embed-text-v2:0",
        {"model_id": PROFILE},
    )


def test_system_inference_profile_also_routes() -> None:
    arn = "arn:aws:bedrock:us-west-2:111122223333:inference-profile/us.cohere.embed-v4:0"
    model, extra = bedrock_embedding_route(f"bedrock/{arn}", {"bedrock_base_model": "cohere.embed-v4:0"})
    assert model == "bedrock/cohere.embed-v4:0"
    assert extra == {"model_id": arn}


def test_plain_models_pass_through() -> None:
    assert bedrock_embedding_route("bedrock/amazon.titan-embed-text-v2:0", None) == (
        "bedrock/amazon.titan-embed-text-v2:0",
        {},
    )
    assert bedrock_embedding_route("openai/text-embedding-3-small", None) == (
        "openai/text-embedding-3-small",
        {},
    )


def test_profile_without_base_model_explains_the_fix() -> None:
    with pytest.raises(EmbeddingConfigurationError, match="bedrock_base_model"):
        bedrock_embedding_route(f"bedrock/{PROFILE}", {})


def test_embed_texts_sync_sends_routed_model_and_profile_id() -> None:
    response = SimpleNamespace(
        data=[{"embedding": [0.1, 0.2, 0.3]}],
        usage=SimpleNamespace(prompt_tokens=3, total_tokens=3),
    )
    with patch("backfield_ai.embeddings.litellm.embedding", return_value=response) as call:
        result = embed_texts_sync(
            litellm_model=f"bedrock/{PROFILE}",
            texts=["Echo Park Lake"],
            api_key="bearer",
            track_attempt=False,
            model_config_json=TITAN,
        )
    kwargs = call.call_args.kwargs
    assert kwargs["model"] == "bedrock/amazon.titan-embed-text-v2:0"
    assert kwargs["model_id"] == PROFILE
    assert result.items[0].vector == [0.1, 0.2, 0.3]
    assert result.dimensions == 3


def test_configured_dimensions_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(EMBEDDING_DIMENSIONS_ENV, raising=False)
    assert configured_embedding_dimensions() == 1536
    monkeypatch.setenv(EMBEDDING_DIMENSIONS_ENV, "1024")
    assert configured_embedding_dimensions() == 1024
    monkeypatch.setenv(EMBEDDING_DIMENSIONS_ENV, "big")
    with pytest.raises(ValueError):
        configured_embedding_dimensions()


def test_every_embedding_column_is_listed_for_resizing() -> None:
    from backfield_db import (
        SubstrateArticleEmbedding,
        SubstrateImageEmbedding,
        SubstrateLocationSemanticDocument,
        SubstrateOrganizationSemanticDocument,
        SubstratePersonSemanticDocument,
    )

    tables = {
        model.__tablename__
        for model in (
            SubstrateArticleEmbedding,
            SubstrateImageEmbedding,
            SubstratePersonSemanticDocument,
            SubstrateLocationSemanticDocument,
            SubstrateOrganizationSemanticDocument,
        )
    }
    assert {table for table, _ in EMBEDDING_VECTOR_COLUMNS} == tables
