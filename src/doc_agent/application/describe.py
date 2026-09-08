"""Describe a document before reading it, whatever format it is.

One question is worth asking of any file: is what I am about to read the whole of it, and
is it settled? A hidden worksheet, a slide set never to show, text marked deleted but
still present, a scanned page with no text -- different formats, same finding, so they
answer in the same field.

Format-specific depth sits beside that common answer rather than replacing it: a
spreadsheet also reports how it calculates, a document its tracked changes. Nothing is
invented for a format that has no such notion.
"""

from __future__ import annotations

from typing import Any, cast

from doc_agent.ports.repositories import DocumentRepository, Record

#: Sections that are only meaningful for the format that records them. A key absent from
#: a document's metadata is left out of the answer rather than reported as empty.
_FORMAT_SECTIONS: tuple[str, ...] = (
    # Spreadsheet
    "calculation",
    "defined_names",
    "sheet_count",
    # Document
    "protection",
    "revisions",
    "hidden_text_runs",
    "fields",
    # Deck
    "slide_count",
    "hidden_slides",
    "slide_size",
    # PDF
    "page_count",
    "encrypted",
    "permissions",
    "form_field_count",
    "pages_without_text",
)

_FORMAT_NAMES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "application/pdf": "pdf",
}


class DescribeDocument:
    """Answer what a document is and whether reading it will show all of it."""

    def __init__(self, repository: DocumentRepository) -> None:
        self.repository = repository

    def execute(self, document_id: str, *, version_id: str | None = None) -> Record:
        metadata = self.repository.get_version_metadata(document_id, version_id=version_id)
        document = self.repository.get_document(document_id)
        read_version = version_id or document.current_version_id
        described: Record = {
            "document_id": document_id,
            "logical_name": document.logical_name,
            "media_type": document.media_type,
            "format": _FORMAT_NAMES.get(document.media_type, "unknown"),
            "version_id": read_version,
            "is_current_version": read_version == document.current_version_id,
            "properties": metadata.get("properties") or {},
            # The common answer, in the same words for every format.
            "withheld_content": metadata.get("withheld_content"),
        }
        for key in _FORMAT_SECTIONS:
            if key in metadata:
                described[key] = metadata[key]

        calculation = metadata.get("calculation")
        if (
            isinstance(calculation, dict)
            and cast(dict[str, Any], calculation).get("automatic") is False
        ):
            described["cached_value_warning"] = (
                "This workbook calculates manually, so a cached formula result may never "
                "have been recalculated by its author. Treat every cached value as the "
                "last saved value, not a current one."
            )
        fields = metadata.get("fields")
        if isinstance(fields, list) and cast(list[Any], fields):
            described["cached_value_warning"] = (
                "Field results in this document are saved values, not recalculated ones: "
                "a date or cross-reference may be as old as the last edit in Word."
            )
        if "withheld_content" not in metadata:
            # Versions stored before these facts were extracted cannot answer, which is
            # not the same as a file with nothing hidden.
            described["settings_available"] = False
            described["settings_note"] = (
                "This version was extracted before document-level facts were captured, so "
                "hidden content, restrictions, and revisions are unknown rather than "
                "absent. Re-ingest the source file to record them."
            )
        return described
