"""Voyage AI as an embedding provider: presets, credentials, routing, and vector size."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from backfield_ai.constants import (
    AI_MODEL_KIND_EMBEDDING,
    AI_PROVIDER_SLUG_BY_INTEGRATION_KEY,
    INTEGRATION_KEY_AI_PROVIDER_VOYAGE,
    is_built_in_ai_provider_integration_key,
)
from backfield_ai.credentials import organization_llm_api_keys
from backfield_ai.curated_catalog import list_curated_templates
from backfield_ai.embeddings import embed_texts_sync
from backfield_ai.litellm_model import litellm_model_id
from backfield_db.pgvector import EMBEDDING_DIMENSIONS_ENV

COST_MAP = {
    "voyage/voyage-4": {"mode": "embedding"},
    "voyage/voyage-4-large": {"mode": "embedding"},
    "voyage/voyage-4-lite": {"mode": "embedding"},
    "voyage/voyage-3.5": {"mode": "embedding"},
    "voyage/voyage-context-4": {"mode": "embedding"},
    "voyage/voyage-code-3": {"mode": "embedding"},
    "voyage/rerank-2.5": {"mode": "rerank"},
}


def test_presets_list_current_general_voyage_models_only() -> None:
    voyage = {
        t.provider_model_id: t
        for t in list_curated_templates(COST_MAP).values()
        if t.provider == "voyage"
    }
    assert set(voyage) == {"voyage-4", "voyage-4-large", "voyage-4-lite"}
    assert voyage["voyage-4-large"].label == "Voyage 4 Large"
    assert all(t.model_kind == AI_MODEL_KIND_EMBEDDING for t in voyage.values())


def test_voyage_routes_through_litellm_prefix() -> None:
    assert litellm_model_id("voyage", "voyage-4-large") == "voyage/voyage-4-large"


def test_voyage_provider_key_maps_to_env_name() -> None:
    assert is_built_in_ai_provider_integration_key(INTEGRATION_KEY_AI_PROVIDER_VOYAGE)
    assert AI_PROVIDER_SLUG_BY_INTEGRATION_KEY[INTEGRATION_KEY_AI_PROVIDER_VOYAGE] == "voyage"
    session = MagicMock()
    session.exec.return_value.all.return_value = [
        SimpleNamespace(integration_key=INTEGRATION_KEY_AI_PROVIDER_VOYAGE, value_encrypted="v")
    ]
    with (
        patch("backfield_ai.credentials.fernet_from_env", return_value=object()),
        patch("backfield_ai.credentials.decrypt_secret", side_effect=lambda v: f"plain-{v}"),
    ):
        assert organization_llm_api_keys(session, 1) == {"VOYAGE_API_KEY": "plain-v"}


def test_voyage_requests_the_configured_vector_size(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(EMBEDDING_DIMENSIONS_ENV, "1024")
    response = SimpleNamespace(
        data=[{"embedding": [0.0] * 1024}],
        usage=SimpleNamespace(prompt_tokens=3, total_tokens=3),
    )
    with patch("backfield_ai.embeddings.litellm.embedding", return_value=response) as call:
        result = embed_texts_sync(
            litellm_model="voyage/voyage-4-large",
            texts=["Echo Park Lake"],
            api_key="voyage-key",
            track_attempt=False,
        )
    assert call.call_args.kwargs["dimensions"] == 1024
    assert call.call_args.kwargs["model"] == "voyage/voyage-4-large"
    assert result.dimensions == 1024


def test_other_providers_do_not_get_a_size_parameter() -> None:
    response = SimpleNamespace(data=[{"embedding": [0.1]}], usage=None)
    with patch("backfield_ai.embeddings.litellm.embedding", return_value=response) as call:
        embed_texts_sync(
            litellm_model="openai/text-embedding-3-small",
            texts=["x"],
            api_key="k",
            track_attempt=False,
        )
    assert "dimensions" not in call.call_args.kwargs
