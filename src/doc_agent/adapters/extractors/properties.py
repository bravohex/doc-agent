"""Document-level facts every format can answer, in one vocabulary.

The workbook work established a theme worth carrying across formats: content that is
present but not visible, and content that looks settled but is not. A hidden worksheet, a
slide set never to show, text marked deleted but still in the file -- these are the same
finding wearing different clothes, so they are reported in the same words.

What does not transfer is left alone. A spreadsheet's cell grid, its validation rules and
its calculation mode have no counterpart in a document or a deck, and inventing one would
put structure into a format that never had it.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any


def core_properties(properties: Any) -> dict[str, Any]:
    """Read the OOXML core properties that say who last touched a file.

    Provenance, not content: useful when a reviewer needs to know which copy of a
    document they are holding. Every field is optional in the format, so anything
    missing stays absent rather than being filled in.
    """

    recorded: dict[str, Any] = {}
    for name, attribute in (
        ("author", "author"),
        ("last_modified_by", "last_modified_by"),
        ("title", "title"),
        ("subject", "subject"),
        ("revision", "revision"),
        ("created", "created"),
        ("modified", "modified"),
    ):
        value = getattr(properties, attribute, None)
        if value in (None, ""):
            continue
        recorded[name] = value.isoformat() if isinstance(value, datetime | date) else value
    return recorded


def withheld(*findings: str | None) -> list[str]:
    """Collect the reasons a reader might not see everything the file contains.

    Stated as sentences rather than flags because each one is a different kind of
    hiding, and a caller should not have to know which fields to compare to notice
    that any of it happened.
    """

    return [finding for finding in findings if finding]
