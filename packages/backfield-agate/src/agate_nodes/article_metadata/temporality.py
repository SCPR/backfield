"""Temporality preset post-processing: evergreen-first fields and their companion rows.

The flow the preset serves (LAist, 2026-11-09): an evergreen story stays a recommendation
candidate; otherwise it stays one only while it is about a current event (judged at
recommendation time, from storylines and age); otherwise it is not a candidate. This module
enforces the owner's rules whatever the model says: evergreen needs evidence (a low-confidence
evergreen is news), no date at low confidence, and every missing or invalid field takes the
safer value. Malformed stale dates and dates before publication are dropped.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

NEWSROOM_TZ = ZoneInfo("America/Los_Angeles")
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Word confidences (high / medium / low) stored on Backfield's 0-1 scale.
CONFIDENCE_WORDS: dict[str, float] = {"high": 0.9, "medium": 0.6, "low": 0.3}

NOT_APPLICABLE = "not_applicable"
EVENT_KINDS = ("one_off", "ongoing")

# Companion rows, one per field, always written (``not_applicable`` when the field does not
# apply) so a rerun that changes the category replaces the old row instead of leaving it.
COMPANION_FIELDS = ("event_kind", "stale_after", "occasion", "perishable_details")


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


def _is_low(raw_confidence: Any) -> bool:
    return isinstance(raw_confidence, str) and raw_confidence.strip().lower() == "low"


def normalize_temporality(
    *,
    category: str,
    raw_confidence: Any,
    response: dict[str, Any],
    publish_date: str | None,
) -> dict[str, Any]:
    """Validated temporality fields for one story. Returns category (possibly adjusted),
    event_kind, stale_after, stale_after_basis, occasion, perishable_details, adjustments."""
    adjustments: list[str] = []
    low = _is_low(raw_confidence)

    if category == "evergreen" and low:
        category = "news"
        adjustments.append("low-confidence-evergreen-is-news")

    out: dict[str, Any] = {
        "category": category,
        "event_kind": None,
        "stale_after": None,
        "stale_after_basis": None,
        "stale_after_rejected": None,
        "occasion": None,
        "perishable_details": None,
    }

    if category == "news":
        kind = response.get("event_kind")
        if kind in EVENT_KINDS:
            out["event_kind"] = kind
        else:
            out["event_kind"] = "one_off"  # shortest currency window: the safe default
            adjustments.append("event-kind-defaulted")
        date_fields = normalize_expiry(
            response.get("stale_after"), response.get("stale_after_basis"), publish_date
        )
        if date_fields["expires_after"] and low:
            date_fields = {
                "expires_after": None,
                "expiry_basis": None,
                "expiry_rejected": "low-confidence",
            }
        out["stale_after"] = date_fields["expires_after"]
        out["stale_after_basis"] = date_fields["expiry_basis"]
        out["stale_after_rejected"] = date_fields["expiry_rejected"]
    else:
        perishable = response.get("perishable_details")
        if isinstance(perishable, bool):
            out["perishable_details"] = perishable
        else:
            out["perishable_details"] = True  # unknown: review it, the safe default
            adjustments.append("perishable-defaulted")
        if category == "seasonal":
            occasion = response.get("occasion")
            if isinstance(occasion, str) and occasion.strip():
                out["occasion"] = occasion.strip()
            else:
                out["occasion"] = "unspecified"
                adjustments.append("occasion-missing")

    out["adjustments"] = adjustments
    return out


def companion_blocks(
    *,
    meta_type: str,
    fields: dict[str, Any],
    confidence: float,
    prompt_preset: str,
) -> list[dict[str, Any]]:
    """One ``<meta_type>_<field>`` metadata row per companion field."""
    values = {
        "event_kind": fields["event_kind"],
        "stale_after": fields["stale_after"] or ("none" if fields["category"] == "news" else None),
        "occasion": fields["occasion"],
        "perishable_details": (
            None
            if fields["perishable_details"] is None
            else ("yes" if fields["perishable_details"] else "no")
        ),
    }
    rationales = {
        "event_kind": "One-off event or ongoing situation.",
        "stale_after": fields["stale_after_basis"] or "No confident publication-relative date.",
        "occasion": "Recurring occasion the story is tied to.",
        "perishable_details": "Whether usefulness depends on specifics that change.",
    }
    blocks = []
    for field in COMPANION_FIELDS:
        value = values[field]
        blocks.append(
            {
                "meta_type": f"{meta_type}_{field}",
                "category": value if value else NOT_APPLICABLE,
                "rationale": rationales[field] if value else "Does not apply to this category.",
                "confidence": confidence,
                "prompt_preset": prompt_preset,
            }
        )
    return blocks
