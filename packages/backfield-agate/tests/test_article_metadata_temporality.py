"""Temporality preset: publish date in the prompt, word confidences, and the expiry companion."""

from __future__ import annotations

import json
from unittest.mock import patch

from agate_nodes.article_metadata.expiry import (
    normalize_expiry,
    resolve_publish_date,
)
from agate_runtime import Edge, GraphSpec, NodeConfig, execute_graph

ARTICLE = {
    "headline": "How to watch the Emmys",
    "text": "The Emmys will air on Monday at 5 p.m. Pacific on ABC.",
    "pub_date": "2026-01-14",
}


def _spec() -> GraphSpec:
    return GraphSpec(
        name="temporality",
        nodes=[
            NodeConfig(id="a", type="JSONInput", params=dict(ARTICLE)),
            NodeConfig(id="b", type="ArticleMetadata", params={"prompt_preset": "temporality"}),
            NodeConfig(
                id="c",
                type="DBOutput",
                params={"stylebook_matching_enabled": False, "semantic_indexing_enabled": False},
            ),
        ],
        edges=[
            Edge(source="a", target="b", sourceHandle="text", targetHandle="text"),
            Edge(source="b", target="c", sourceHandle="text", targetHandle="data"),
        ],
    )


def _run(answer: dict) -> tuple[dict, str]:
    with patch(
        "agate_nodes.article_metadata.node_port.call_llm",
        return_value=json.dumps(answer),
    ) as llm:
        out = execute_graph(_spec())
    return out["stylebook_output"]["article_metadata"], llm.call_args.kwargs["prompt"]


def test_resolve_publish_date_prefers_pub_date() -> None:
    assert (
        resolve_publish_date({"pub_date": "2026-01-14", "published": "2026-01-15T07:00:00+00:00"})
        == "2026-01-14"
    )


def test_resolve_publish_date_converts_utc_to_los_angeles() -> None:
    # 2026-01-15 03:00 UTC is still Jan 14 in Los Angeles.
    assert resolve_publish_date({"published": "2026-01-15T03:00:00Z"}) == "2026-01-14"
    assert resolve_publish_date({"published": 1768446000000}) == "2026-01-14"
    assert resolve_publish_date({}) is None


def test_normalize_expiry_rules() -> None:
    assert normalize_expiry(None, None, "2026-01-14")["expires_after"] is None
    assert normalize_expiry("Jan 16", "on Monday", "2026-01-14")["expiry_rejected"] == "malformed"
    before = normalize_expiry("2026-01-10", "last week", "2026-01-14")
    assert before["expires_after"] is None
    assert before["expiry_rejected"] == "before-publish-date"
    ok = normalize_expiry("2026-01-19", " will air on Monday ", "2026-01-14")
    assert ok == {
        "expires_after": "2026-01-19",
        "expiry_basis": "will air on Monday",
        "expiry_rejected": None,
    }


def test_temporality_preset_classifies_with_expiry() -> None:
    meta, prompt = _run(
        {
            "category": "supersedable",
            "confidence": "high",
            "rationale": "Hinges on the Emmys airing Monday.",
            "expires_after": "2026-01-19",
            "expiry_basis": "will air on Monday",
        }
    )
    assert "## Publish Date\n\n2026-01-14" in prompt
    assert "expires_after, expiry_basis" in prompt
    assert meta["meta_type"] == "temporality"
    assert meta["category"] == "supersedable"
    assert meta["confidence"] == 0.9
    assert meta["expires_after"] == "2026-01-19"
    assert meta["companion_blocks"] == [
        {
            "meta_type": "temporality_expiry",
            "category": "2026-01-19",
            "rationale": "will air on Monday",
            "confidence": 0.9,
            "prompt_preset": "temporality",
        }
    ]


def test_temporality_preset_without_expiry_records_none() -> None:
    meta, _ = _run(
        {
            "category": "recurring-instance",
            "confidence": "low",
            "rationale": "Annual awards coverage.",
            "expires_after": "2026-01-01",
            "expiry_basis": "last year",
        }
    )
    assert meta["category"] == "recurring_instance"
    assert meta["confidence"] == 0.3
    assert meta["expiry_rejected"] == "before-publish-date"
    companion = meta["companion_blocks"][0]
    assert companion["category"] == "none"
    assert companion["meta_type"] == "temporality_expiry"
