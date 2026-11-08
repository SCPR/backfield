"""Web search provider choice (Brave vs Exa) and the Exa organization integration key."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from backfield_ai.constants import (
    INTEGRATION_KEY_PLATFORM_BRAVE_SEARCH,
    INTEGRATION_KEY_PLATFORM_EXA_SEARCH,
    ORG_PLATFORM_INTEGRATION_KEYS,
    is_platform_integration_key,
)
from backfield_ai.credentials import organization_platform_env_keys
from pydantic import ValidationError


def _warm_geocode_import_graph() -> None:
    """Prime runner imports so the geocode node loads without a cycle (as other tests do)."""
    from agate_runtime.nodes.geocode_agent import run_geocode_agent  # noqa: F401


def select_web_search_keys(provider, brave, exa):
    _warm_geocode_import_graph()
    from agate_nodes.geocode_agent.node import select_web_search_keys as select

    return select(provider, brave, exa)


def _params(**kwargs):
    _warm_geocode_import_graph()
    from agate_nodes.geocode_agent.node import GeocodeAgentParams

    return GeocodeAgentParams(**kwargs)


def test_auto_passes_both_keys() -> None:
    assert select_web_search_keys("auto", "brave-key", "exa-key") == ("brave-key", "exa-key")


def test_brave_withholds_exa_key() -> None:
    assert select_web_search_keys("brave", "brave-key", "exa-key") == ("brave-key", None)


def test_exa_withholds_brave_key() -> None:
    assert select_web_search_keys("exa", "brave-key", "exa-key") == (None, "exa-key")


def test_chosen_provider_without_key_leaves_duckduckgo_only() -> None:
    assert select_web_search_keys("exa", "brave-key", None) == (None, None)
    assert select_web_search_keys("brave", None, "exa-key") == (None, None)


def test_params_default_to_auto_and_reject_unknown_provider() -> None:
    assert _params().webSearchProvider == "auto"
    assert _params(webSearchProvider="exa").webSearchProvider == "exa"
    with pytest.raises(ValidationError):
        _params(webSearchProvider="bing")


def test_exa_is_an_organization_platform_key() -> None:
    assert INTEGRATION_KEY_PLATFORM_EXA_SEARCH == "platform.search.exa"
    assert INTEGRATION_KEY_PLATFORM_EXA_SEARCH in ORG_PLATFORM_INTEGRATION_KEYS
    assert is_platform_integration_key(INTEGRATION_KEY_PLATFORM_EXA_SEARCH)


def test_organization_exa_secret_maps_to_worker_env_name() -> None:
    rows = [
        SimpleNamespace(integration_key=INTEGRATION_KEY_PLATFORM_BRAVE_SEARCH, value_encrypted="b"),
        SimpleNamespace(integration_key=INTEGRATION_KEY_PLATFORM_EXA_SEARCH, value_encrypted="e"),
    ]
    session = MagicMock()
    session.exec.return_value.all.return_value = rows
    with (
        patch("backfield_ai.credentials.fernet_from_env", return_value=object()),
        patch("backfield_ai.credentials.decrypt_secret", side_effect=lambda v: f"plain-{v}"),
    ):
        env = organization_platform_env_keys(session, organization_id=1)
    assert env == {"BRAVE_SEARCH_API_KEY": "plain-b", "EXA_API_KEY": "plain-e"}
