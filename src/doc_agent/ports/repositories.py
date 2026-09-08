"""Persistence port used by application services."""

from __future__ import annotations

from typing import Any, Protocol

from doc_agent.domain.models import (
    Block,
    Change,
    DocumentSummary,
    ExtractedDocument,
    Project,
    StoredVersion,
)

type Record = dict[str, Any]


def row_cursor(record: Record) -> str:
    """Encode a page boundary that cannot skip a row or straddle a version.

    ``ordinal`` numbers rows inside their own sheet, so a workbook repeats it once per
    sheet: paging on ordinal alone dropped every row sharing one with an earlier sheet.
    A stable key is unique within a version, so the pair is a total order.

    The version travels in the cursor too, which is what keeps a paged read consistent:
    if the document is re-ingested midway, later pages continue from the version the
    first page was read from instead of silently mixing two.
    """

    return f"{record['version_id']}:{int(record['ordinal'])}:{record['stable_key']}"


def decode_cursor(after: str | None) -> tuple[str, int, str] | None:
    """Read a boundary produced by :func:`row_cursor`, refusing anything else.

    A cursor the caller invented cannot be honoured silently: it would page from a
    position this API never handed out.
    """

    if not after:
        return None
    parts = after.split(":", 2)
    if len(parts) != 3 or not parts[0] or not parts[1].strip().lstrip("-").isdigit():
        raise ValueError(f"Cursor is not a page boundary produced by this API: {after!r}")
    version_id, ordinal, stable_key = parts
    return version_id, int(ordinal), stable_key


class DocumentRepository(Protocol):
    """Persist projects, immutable versions, blocks, visuals, and history."""

    def create_project(self, name: str) -> Project: ...
    def list_projects(self) -> list[Project]: ...
    def get_project(self, project_id: str) -> Project: ...
    def get_document(self, document_id: str) -> DocumentSummary: ...
    def list_documents(self, project_id: str) -> list[DocumentSummary]: ...
    def find_document(self, project_id: str, logical_name: str) -> DocumentSummary | None: ...
    def set_document_active(self, document_id: str, *, active: bool) -> DocumentSummary: ...
    def delete_document(self, document_id: str) -> DocumentSummary: ...
    def current_blocks(self, document_id: str) -> list[Block]: ...
    def save_version(
        self,
        project_id: str,
        document: ExtractedDocument,
        source_sha256: str,
        changes: list[Change],
        *,
        document_id: str | None = None,
    ) -> StoredVersion: ...
    def history(self, document_id: str) -> list[StoredVersion]: ...
    def get_changes(self, document_id: str, version_number: int) -> list[Change]: ...
    def project_blocks(self, project_id: str) -> list[Record]: ...
    def get_block(self, block_id: str, *, version_id: str | None = None) -> Record: ...
    def list_visuals(self, document_id: str, *, version_id: str | None = None) -> list[Record]: ...
    def get_table_rows(
        self,
        document_id: str,
        *,
        version_id: str | None = None,
        after: str | None = None,
        limit: int | None = None,
    ) -> list[Record]: ...
    def get_sheet_rows(
        self,
        document_id: str,
        sheet: str,
        *,
        version_id: str | None = None,
        min_row: int = 1,
        max_row: int | None = None,
        after: str | None = None,
        limit: int | None = None,
    ) -> list[Record]: ...
    def list_containers(
        self, document_id: str, *, version_id: str | None = None
    ) -> list[Record]: ...
    def get_version_metadata(
        self, document_id: str, *, version_id: str | None = None
    ) -> Record: ...
    def update_visual(
        self, visual_id: str, *, decorative: bool, retrieval_enabled: bool, summary: str | None
    ) -> None: ...
