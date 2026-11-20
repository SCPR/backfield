"""Kinds of content stored as ``substrate_article`` rows."""

from __future__ import annotations

from enum import StrEnum


class ContentType(StrEnum):
    """What kind of content an item is, independent of its outlet (``external_source``).

    Add a value here alongside the flow that produces the new kind of content.
    """

    ARTICLE = "article"
    SHOW_SEGMENT = "show_segment"


DEFAULT_CONTENT_TYPE: ContentType = ContentType.ARTICLE
