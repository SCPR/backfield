"""Temporality preset (evergreen-first): publish date in the prompt, word confidences, the
evergreen / seasonal / news category, and the companion rows for its side fields."""

from __future__ import annotations

import json
from unittest.mock import patch

from agate_nodes.article_metadata.temporality import (
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


def _answer(**overrides: object) -> dict:
    base = {
        "category": "news",
        "confidence": "high",
        "rationale": "Previews the Emmys broadcast Monday.",
        "evidence": "will air on Monday",
        "event_kind": "one_off",
        "stale_after": "2026-01-19",
        "stale_after_basis": "will air on Monday",
        "perishable_details": None,
        "occasion": None,
    }
    base.update(overrides)
    return base


def _companions(meta: dict) -> dict[str, str]:
    return {b["meta_type"]: b["category"] for b in meta["companion_blocks"]}


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


def test_stale_date_validation() -> None:
    assert normalize_expiry(None, None, "2026-01-14")["expires_after"] is None
    assert normalize_expiry("Jan 16", "on Monday", "2026-01-14")["expiry_rejected"] == "malformed"
    before = normalize_expiry("2026-01-10", "last week", "2026-01-14")
    assert before["expires_after"] is None
    assert before["expiry_rejected"] == "before-publish-date"


def test_news_with_a_confident_date() -> None:
    meta, prompt = _run(_answer())
    assert "## Publish Date\n\n2026-01-14" in prompt
    assert "evidence, event_kind, stale_after" in prompt
    assert meta["category"] == "news"
    assert meta["confidence"] == 0.9
    assert meta["event_kind"] == "one_off"
    assert meta["stale_after"] == "2026-01-19"
    assert meta["evidence"] == "will air on Monday"
    assert _companions(meta) == {
        "temporality_event_kind": "one_off",
        "temporality_stale_after": "2026-01-19",
        "temporality_occasion": "not_applicable",
        "temporality_perishable_details": "not_applicable",
    }


def test_low_confidence_evergreen_becomes_news_without_a_date() -> None:
    meta, _ = _run(
        _answer(category="evergreen", confidence="low", event_kind=None, perishable_details=False)
    )
    assert meta["category"] == "news"
    assert "low-confidence-evergreen-is-news" in meta["adjustments"]
    assert meta["event_kind"] == "one_off"
    assert meta["stale_after"] is None
    assert meta["stale_after_rejected"] == "low-confidence"


def test_ongoing_news_without_a_date_stores_none() -> None:
    meta, _ = _run(_answer(event_kind="ongoing", stale_after=None, stale_after_basis=None))
    companions = _companions(meta)
    assert companions["temporality_event_kind"] == "ongoing"
    assert companions["temporality_stale_after"] == "none"


def test_evergreen_ignores_news_fields() -> None:
    meta, _ = _run(_answer(category="evergreen", perishable_details=False))
    assert meta["category"] == "evergreen"
    assert meta["event_kind"] is None
    assert meta["stale_after"] is None
    assert _companions(meta) == {
        "temporality_event_kind": "not_applicable",
        "temporality_stale_after": "not_applicable",
        "temporality_occasion": "not_applicable",
        "temporality_perishable_details": "no",
    }


def test_seasonal_keeps_occasion_and_defaults_perishable_to_review() -> None:
    meta, _ = _run(_answer(category="seasonal", occasion="Thanksgiving", perishable_details=None))
    assert meta["occasion"] == "Thanksgiving"
    assert meta["perishable_details"] is True
    assert "perishable-defaulted" in meta["adjustments"]
    assert _companions(meta)["temporality_occasion"] == "Thanksgiving"


def test_invalid_event_kind_defaults_to_one_off() -> None:
    meta, _ = _run(_answer(event_kind="sometimes"))
    assert meta["event_kind"] == "one_off"
    assert "event-kind-defaulted" in meta["adjustments"]
