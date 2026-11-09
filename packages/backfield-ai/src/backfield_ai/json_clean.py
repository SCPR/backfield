"""Strip markdown fences from LLM JSON-ish responses (parity with Agate helpers)."""

import json
import re

_FENCED_BLOCK_RE = re.compile(r"```(?:json)?\s*\n?(.*?)```", re.DOTALL)


def _parses(text: str) -> bool:
    try:
        json.loads(text)
    except ValueError:
        return False
    return True


def _largest_embedded_json(text: str) -> str | None:
    """Longest JSON object or array embedded in prose, or None."""
    decoder = json.JSONDecoder()
    best: str | None = None
    i = 0
    while i < len(text):
        if text[i] not in "{[":
            i += 1
            continue
        try:
            _, end = decoder.raw_decode(text, i)
        except ValueError:
            i += 1
            continue
        candidate = text[i:end]
        if best is None or len(candidate) > len(best):
            best = candidate
        i = end
    return best


def clean_json_response_text(response_text: str) -> str:
    """Return the JSON payload of a model response.

    Strips surrounding markdown fences. When the result still isn't JSON (models without a
    provider JSON mode, such as Claude through a Bedrock application inference profile, may
    explain their reasoning before or after the JSON), fall back to a fenced block anywhere in
    the text, then to the largest JSON object or array embedded in it. Text with no JSON is
    returned stripped, so callers still see the original parse error.
    """
    cleaned = response_text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()
    if not cleaned or _parses(cleaned):
        return cleaned

    for block in _FENCED_BLOCK_RE.findall(response_text):
        block = block.strip()
        if _parses(block):
            return block

    embedded = _largest_embedded_json(response_text)
    return embedded if embedded is not None else cleaned
