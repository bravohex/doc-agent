"""Default local analyzer that never transmits visual content externally."""

from __future__ import annotations


class NullVisualAnalyzer:
    """Return nearby source text only; external vision is an opt-in adapter."""

    def summarize(self, data: bytes, *, media_type: str, nearby_text: str = "") -> str | None:
        del data, media_type
        return nearby_text.strip() or None
