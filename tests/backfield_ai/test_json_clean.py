"""Tests for extracting JSON payloads from model responses."""

from __future__ import annotations

import json

import pytest
from backfield_ai.json_clean import clean_json_response_text


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ('{"a": 1}', '{"a": 1}'),
        ('```json\n{"a": 1}\n```', '{"a": 1}'),
        ('```\n[1, 2]\n```', "[1, 2]"),
        ("  plain text  ", "plain text"),
        ("", ""),
    ],
)
def test_existing_fence_behavior_is_unchanged(raw: str, expected: str) -> None:
    assert clean_json_response_text(raw) == expected


def test_extracts_json_after_prose() -> None:
    raw = (
        "Eastside is a loose term, so I drew the box around Boyle Heights and East LA.\n\n"
        '{"bounding_box": [34.0, -118.27, 34.09, -118.12], "confidence": "medium"}'
    )
    assert json.loads(clean_json_response_text(raw)) == {
        "bounding_box": [34.0, -118.27, 34.09, -118.12],
        "confidence": "medium",
    }


def test_prefers_fenced_block_inside_prose() -> None:
    raw = 'Here is the result {not json}:\n```json\n{"ok": true}\n```\nLet me know.'
    assert clean_json_response_text(raw) == '{"ok": true}'


def test_picks_largest_embedded_object() -> None:
    raw = 'Using {"x": 1} as a hint, the answer is {"locations": [{"name": "Pasadena"}]}.'
    assert json.loads(clean_json_response_text(raw)) == {"locations": [{"name": "Pasadena"}]}


def test_truncated_json_still_fails_to_parse() -> None:
    raw = '{"locations": [["Southern California", "rs"'
    with pytest.raises(json.JSONDecodeError):
        json.loads(clean_json_response_text(raw))
