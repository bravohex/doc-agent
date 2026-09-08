"""The one description that works for any format.

A caller should be able to ask "will reading this show me all of it?" without knowing
which format it is, and should get format-specific depth only where the format has it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from doc_agent.adapters.sqlite.connection import SqliteDatabase
from doc_agent.adapters.sqlite.repository import SqliteRepository
from doc_agent.application.describe import DescribeDocument
from doc_agent.domain.models import ExtractedDocument

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _describe(tmp_path: Path, *documents: ExtractedDocument) -> tuple[DescribeDocument, list[str]]:
    repository = SqliteRepository(SqliteDatabase(tmp_path / "knowledge.sqlite"))
    project = repository.create_project("Horizontal")
    ids = [
        repository.save_version(project.id, document, f"sha-{index}", changes=[]).document_id
        for index, document in enumerate(documents)
    ]
    return DescribeDocument(repository), ids


def _document(name: str, media_type: str, metadata: dict[str, Any]) -> ExtractedDocument:
    return ExtractedDocument(logical_name=name, media_type=media_type, metadata=metadata)


def test_every_format_answers_withheld_content_in_the_same_field(tmp_path: Path) -> None:
    describe, ids = _describe(
        tmp_path,
        _document(
            "book.xlsx",
            XLSX,
            {"withheld_content": ["Sheet(s) Internal are hidden"], "sheet_count": 3},
        ),
        _document(
            "deed.docx",
            DOCX,
            {
                "withheld_content": ["1 tracked deletion(s) are still in the file"],
                "revisions": {"deletions": 1, "insertions": 0, "authors": [], "deleted_text": []},
            },
        ),
    )

    workbook = describe.execute(ids[0])
    deed = describe.execute(ids[1])

    assert workbook["format"] == "xlsx"
    assert deed["format"] == "docx"
    for described in (workbook, deed):
        assert described["withheld_content"], "the shared finding is missing"


def test_format_sections_appear_only_for_the_format_that_records_them(tmp_path: Path) -> None:
    """Nothing is invented for a format that has no such notion."""

    describe, ids = _describe(
        tmp_path,
        _document(
            "book.xlsx",
            XLSX,
            {
                "withheld_content": [],
                "calculation": {"mode": "auto", "automatic": True},
                "sheet_count": 2,
            },
        ),
        _document(
            "deed.docx",
            DOCX,
            {"withheld_content": [], "hidden_text_runs": 0, "protection": {"enabled": True}},
        ),
    )

    workbook = describe.execute(ids[0])
    deed = describe.execute(ids[1])

    assert "calculation" in workbook
    assert "revisions" not in workbook and "hidden_text_runs" not in workbook
    assert "protection" in deed
    assert "calculation" not in deed and "sheet_count" not in deed


def test_a_manual_workbook_and_a_field_bearing_document_both_warn_about_saved_values(
    tmp_path: Path,
) -> None:
    """Same hazard, two formats: a value that looks current and is not."""

    describe, ids = _describe(
        tmp_path,
        _document(
            "book.xlsx",
            XLSX,
            {"withheld_content": [], "calculation": {"mode": "manual", "automatic": False}},
        ),
        _document(
            "deed.docx",
            DOCX,
            {
                "withheld_content": [],
                "fields": [
                    {"instruction": "DATE", "result": "01/03/2026", "value_state": "cached"}
                ],
            },
        ),
    )

    assert "recalculated" in describe.execute(ids[0])["cached_value_warning"]
    assert "recalculated" in describe.execute(ids[1])["cached_value_warning"]


def test_a_document_with_nothing_hidden_says_so_rather_than_staying_silent(
    tmp_path: Path,
) -> None:
    describe, ids = _describe(tmp_path, _document("clean.docx", DOCX, {"withheld_content": []}))

    described = describe.execute(ids[0])

    # An empty list is the finding "nothing is hidden".
    assert described["withheld_content"] == []
    assert "settings_available" not in described


def test_a_version_extracted_earlier_reports_unknown_not_nothing_hidden(
    tmp_path: Path,
) -> None:
    """The distinction that matters most here: unknown is not the same as clean."""

    describe, ids = _describe(tmp_path, _document("old.docx", DOCX, {}))

    described = describe.execute(ids[0])

    assert described["withheld_content"] is None
    assert described["settings_available"] is False
    assert "Re-ingest" in described["settings_note"]


@pytest.mark.parametrize("media_type", ["application/octet-stream", "text/plain"])
def test_an_unknown_media_type_is_named_unknown_not_guessed(
    tmp_path: Path, media_type: str
) -> None:
    describe, ids = _describe(
        tmp_path, _document("thing.bin", media_type, {"withheld_content": []})
    )

    assert describe.execute(ids[0])["format"] == "unknown"
