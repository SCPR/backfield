"""Expiry handling for presets whose answer carries ``expires_after`` / ``expiry_basis``.

Mirrors LAist's temporality pipeline: a story's expiry is a publication-relative date the
model resolved from a verbatim phrase. Malformed dates and dates before the publish date
are dropped (the prompt itself says to err toward no expiry).
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from agate_nodes.article_metadata.presets import EXPIRY_NONE, expiry_meta_type

NEWSROOM_TZ = ZoneInfo("America/Los_Angeles")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Word confidences (high / medium / low) stored on Backfield's 0-1 scale.
CONFIDENCE_WORDS: dict[str, float] = {"high": 0.9, "medium": 0.6, "low": 0.3}

NO_EXPIRY_RATIONALE = "No publication-relative expiry."


def resolve_publish_date(flattened: dict[str, Any]) -> str | None:
    """Newsroom-local publish date (YYYY-MM-DD) from the article input, or None.

    Prefers an explicit ``pub_date``; otherwise converts a ``published`` timestamp (ISO
    string or epoch seconds/milliseconds) to the Los Angeles calendar date.
    """
    raw_date = flattened.get("pub_date")
    if isinstance(raw_date, str) and _ISO_DATE.match(raw_date.strip()[:10]):
        return raw_date.strip()[:10]

    raw = flattened.get("published")
    moment: datetime | None = None
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        seconds = raw / 1000 if raw > 1e11 else raw
        moment = datetime.fromtimestamp(seconds, NEWSROOM_TZ)
    elif isinstance(raw, str) and raw.strip():
        text = raw.strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.date().isoformat()
        moment = parsed.astimezone(NEWSROOM_TZ)
    return moment.date().isoformat() if moment else None


def normalize_confidence_words(response_data: Any) -> Any:
    """Map a word confidence (high/medium/low) to the node's numeric scale."""
    if not isinstance(response_data, dict):
        return response_data
    raw = response_data.get("confidence")
    if isinstance(raw, str) and raw.strip().lower() in CONFIDENCE_WORDS:
        return {**response_data, "confidence": CONFIDENCE_WORDS[raw.strip().lower()]}
    return response_data


def normalize_expiry(value: Any, basis: Any, publish_date: str | None) -> dict[str, Any]:
    """Validate a model-proposed expiry. Returns expires_after, expiry_basis, expiry_rejected."""
    if value is None or value == "":
        return {"expires_after": None, "expiry_basis": None, "expiry_rejected": None}
    if not isinstance(value, str) or not _ISO_DATE.match(value.strip()):
        return {"expires_after": None, "expiry_basis": None, "expiry_rejected": "malformed"}
    try:
        expires = date.fromisoformat(value.strip())
    except ValueError:
        return {"expires_after": None, "expiry_basis": None, "expiry_rejected": "unparseable"}
    if publish_date:
        try:
            published = date.fromisoformat(publish_date)
        except ValueError:
            published = None
        if published is not None and expires < published:
            return {
                "expires_after": None,
                "expiry_basis": None,
                "expiry_rejected": "before-publish-date",
            }
    clean_basis = basis.strip() if isinstance(basis, str) and basis.strip() else None
    return {
        "expires_after": expires.isoformat(),
        "expiry_basis": clean_basis,
        "expiry_rejected": None,
    }


def expiry_companion_block(
    *,
    meta_type: str,
    expiry: dict[str, Any],
    confidence: float,
    prompt_preset: str,
) -> dict[str, Any]:
    """The ``<meta_type>_expiry`` metadata row: category is the date, or "none"."""
    expires_after = expiry.get("expires_after")
    if expires_after:
        rationale = expiry.get("expiry_basis") or "Expiry date given without a source phrase."
    else:
        rationale = NO_EXPIRY_RATIONALE
    return {
        "meta_type": expiry_meta_type(meta_type),
        "category": expires_after or EXPIRY_NONE,
        "rationale": rationale,
        "confidence": confidence,
        "prompt_preset": prompt_preset,
    }
