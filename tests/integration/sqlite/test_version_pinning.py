"""Reads can be held to one version of a document.

Without this, two calls either side of an ingest answer from two different states and
nothing says so. Paging is the sharp case: the cursor carries its version, so a sequence
of pages describes one document rather than a blend of two.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from doc_agent.adapters.sqlite.connection import SqliteDatabase
from doc_agent.adapters.sqlite.repository import SqliteRepository
from doc_agent.application.sheets import ReadSheet
from doc_agent.domain.errors import NotFoundError, VersionConflictError
from doc_agent.domain.models import (
    Block,
    BlockKind,
    Container,
    ExtractedDocument,
    XlsxLocator,
)


def _workbook(rows: int, *, sheet: str = "MOG") -> ExtractedDocument:
    return ExtractedDocument(
        logical_name="v.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        containers=[
            Container(
                stable_key=f"sheet-{sheet}",
                kind="worksheet",
                title=sheet,
                ordinal=1,
                source=XlsxLocator(sheet=sheet, row=1, cell_range=f"A1:B{rows}"),
                metadata={"state": "visible", "dimension": f"A1:B{rows}", "tables": []},
            )
        ],
        blocks=[
            Block(
                stable_key=f"row-{row}",
                kind=BlockKind.TABLE_ROW,
                ordinal=row,
                text=f"row {row}",
                source=XlsxLocator(sheet=sheet, row=row, cell_range=f"A{row}:B{row}"),
                payload={"cells": [{"raw_value": f"r{row}", "display": f"r{row}"}]},
                presentation={"cells": [{"coordinate": f"A{row}", "number_format": "General"}]},
            )
            for row in range(1, rows + 1)
        ],
    )


@pytest.fixture
def two_versions(tmp_path: Path) -> tuple[SqliteRepository, ReadSheet, str, str, str]:
    """A document ingested twice: four rows, then nine."""

    repository = SqliteRepository(SqliteDatabase(tmp_path / "knowledge.sqlite"))
    project = repository.create_project("Versions")
    first = repository.save_version(project.id, _workbook(4), "sha-1", changes=[])
    second = repository.save_version(project.id, _workbook(9), "sha-2", changes=[])
    assert first.document_id == second.document_id
    return (
        repository,
        ReadSheet(repository),
        first.document_id,
        first.version_id,
        second.version_id,
    )


def test_reads_default_to_the_current_version(
    two_versions: tuple[SqliteRepository, ReadSheet, str, str, str],
) -> None:
    _, reader, document_id, _, current = two_versions

    page = reader.range(document_id, "MOG")

    assert page["version_id"] == current
    assert page["is_current_version"] is True
    assert len(page["rows"]) == 9


def test_a_pinned_read_returns_that_version_and_says_it_is_not_current(
    two_versions: tuple[SqliteRepository, ReadSheet, str, str, str],
) -> None:
    _, reader, document_id, old, _ = two_versions

    page = reader.range(document_id, "MOG", version_id=old)

    assert page["version_id"] == old
    assert page["is_current_version"] is False
    assert len(page["rows"]) == 4


def test_paging_stays_on_the_version_it_started_from(tmp_path: Path) -> None:
    """The document is re-ingested between two pages; the second must not switch."""

    repository = SqliteRepository(SqliteDatabase(tmp_path / "knowledge.sqlite"))
    reader = ReadSheet(repository)
    project = repository.create_project("Versions")
    first = repository.save_version(project.id, _workbook(4), "sha-1", changes=[])
    document_id = first.document_id

    page_one = reader.range(document_id, "MOG", limit=2)
    assert page_one["is_current_version"] is True

    repository.save_version(project.id, _workbook(9), "sha-2", changes=[])

    page_two = reader.range(document_id, "MOG", limit=2, cursor=page_one["next_cursor"])

    assert page_two["version_id"] == page_one["version_id"]
    # The caller is told the pages now describe history rather than the current document.
    assert page_two["is_current_version"] is False
    assert [row["row"] for row in page_two["rows"]] == [3, 4]

    # Starting over without a cursor reads the new version.
    assert reader.range(document_id, "MOG", limit=2)["is_current_version"] is True


def test_a_cursor_and_a_conflicting_version_are_refused(
    two_versions: tuple[SqliteRepository, ReadSheet, str, str, str],
) -> None:
    """Asking for one version while continuing another is a contradiction, not a choice."""

    _, reader, document_id, old, current = two_versions
    page = reader.range(document_id, "MOG", version_id=old, limit=2)

    with pytest.raises(VersionConflictError, match="Cursor continues"):
        reader.range(document_id, "MOG", cursor=page["next_cursor"], version_id=current)


def test_a_version_from_another_document_is_refused(tmp_path: Path) -> None:
    repository = SqliteRepository(SqliteDatabase(tmp_path / "knowledge.sqlite"))
    project = repository.create_project("Versions")
    mine = repository.save_version(project.id, _workbook(2), "sha-a", changes=[])
    other_document = _workbook(2)
    other_document.logical_name = "other.xlsx"
    theirs = repository.save_version(project.id, other_document, "sha-b", changes=[])

    with pytest.raises(NotFoundError, match="Version not found"):
        repository.get_table_rows(mine.document_id, version_id=theirs.version_id)


def test_sheets_and_blocks_can_be_pinned_too(
    two_versions: tuple[SqliteRepository, ReadSheet, str, str, str],
) -> None:
    repository, reader, document_id, old, _ = two_versions

    assert reader.sheets(document_id, version_id=old)[0]["dimension"] == "A1:B4"
    assert reader.sheets(document_id)[0]["dimension"] == "A1:B9"

    # A block keeps its id across versions, so the version decides which copy is read.
    row = repository.get_table_rows(document_id, version_id=old)[0]
    pinned = repository.get_block(str(row["block_id"]), version_id=old)
    assert pinned["version_id"] == old
