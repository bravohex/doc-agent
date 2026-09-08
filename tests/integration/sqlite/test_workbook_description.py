"""Describing a workbook before reading it, and never guessing what was not recorded.

The distinction that carries the weight here: an empty list means "this sheet has no
such rules", while ``None`` means "this version never recorded whether it does". A store
written before these facts were extracted must report the second, not the first.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from doc_agent.adapters.sqlite.connection import SqliteDatabase
from doc_agent.adapters.sqlite.repository import SqliteRepository
from doc_agent.application.sheets import ReadSheet
from doc_agent.domain.models import Container, ExtractedDocument, XlsxLocator

VALIDATION = {
    "type": "list",
    "operator": None,
    "formula1": '"Open,Closed"',
    "ranges": ["B2:B100"],
    "allow_blank": False,
    "error_title": "Invalid status",
}


def _document(
    *, sheet_metadata: dict[str, Any], document_metadata: dict[str, Any]
) -> ExtractedDocument:
    return ExtractedDocument(
        logical_name="audit.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        containers=[
            Container(
                stable_key="sheet-mog",
                kind="worksheet",
                title="MOG",
                ordinal=1,
                source=XlsxLocator(sheet="MOG", row=1, cell_range="A1:D4"),
                metadata=sheet_metadata,
            )
        ],
        metadata=document_metadata,
    )


def _reader(tmp_path: Path, document: ExtractedDocument) -> tuple[ReadSheet, str]:
    repository = SqliteRepository(SqliteDatabase(tmp_path / "knowledge.sqlite"))
    project = repository.create_project("Audit")
    stored = repository.save_version(project.id, document, "sha", changes=[])
    return ReadSheet(repository), stored.document_id


@pytest.fixture
def modern(tmp_path: Path) -> tuple[ReadSheet, str]:
    return _reader(
        tmp_path,
        _document(
            sheet_metadata={
                "state": "visible",
                "dimension": "A1:D4",
                "tables": [{"name": "FitGap", "ref": "A1:D4"}],
                "validations": [VALIDATION],
                "conditional_formats": [],
                "defined_names": [],
            },
            document_metadata={
                "sheet_count": 1,
                "calculation": {"mode": "manual", "automatic": False},
                "defined_names": [
                    {"name": "TaxRate", "refers_to": "MOG!$C$1", "scope": "workbook"}
                ],
            },
        ),
    )


@pytest.fixture
def legacy(tmp_path: Path) -> tuple[ReadSheet, str]:
    """A version stored before workbook settings and rules were extracted."""

    return _reader(
        tmp_path,
        _document(
            sheet_metadata={"state": "visible", "dimension": "A1:D4", "tables": []},
            document_metadata={"sheet_count": 1},
        ),
    )


def test_the_workbook_reports_its_calculation_mode_and_names(
    modern: tuple[ReadSheet, str],
) -> None:
    reader, document_id = modern

    described = reader.workbook(document_id)

    assert described["calculation"] == {"mode": "manual", "automatic": False}
    assert [n["name"] for n in described["defined_names"]] == ["TaxRate"]
    assert described["sheets"] == [
        {
            "sheet": "MOG",
            "ordinal": 1,
            "hidden": False,
            "dimension": "A1:D4",
            "tables": 1,
            "validations": 1,
            "conditional_formats": 0,
        }
    ]


def test_manual_calculation_warns_about_cached_values(modern: tuple[ReadSheet, str]) -> None:
    """The two facts belong together: manual mode is why a cached value may be stale."""

    reader, document_id = modern

    described = reader.workbook(document_id)

    assert "cached_value_warning" in described
    assert "last saved value" in described["cached_value_warning"]


def test_an_automatic_workbook_carries_no_warning(tmp_path: Path) -> None:
    reader, document_id = _reader(
        tmp_path,
        _document(
            sheet_metadata={"state": "visible", "tables": [], "validations": []},
            document_metadata={"calculation": {"mode": "auto", "automatic": True}},
        ),
    )

    assert "cached_value_warning" not in reader.workbook(document_id)


def test_rules_are_reported_against_the_ranges_they_cover(
    modern: tuple[ReadSheet, str],
) -> None:
    reader, document_id = modern

    sheet = reader.sheets(document_id)[0]

    assert sheet["validations"][0]["ranges"] == ["B2:B100"]
    assert sheet["validations"][0]["formula1"] == '"Open,Closed"'
    # An empty list is a finding: this sheet has no conditional rules.
    assert sheet["conditional_formats"] == []


def test_a_version_extracted_earlier_reports_unknown_not_absent(
    legacy: tuple[ReadSheet, str],
) -> None:
    reader, document_id = legacy

    described = reader.workbook(document_id)
    sheet = reader.sheets(document_id)[0]

    # None, not {} or []: the file may well have rules that were never recorded.
    assert described["calculation"] is None
    assert described["defined_names"] is None
    assert sheet["validations"] is None
    assert sheet["conditional_formats"] is None
    assert described["sheets"][0]["validations"] is None

    # And it says why, with the way out.
    assert described["settings_available"] is False
    assert "Re-ingest" in described["settings_note"]
    # Nothing is warned about, because nothing is known.
    assert "cached_value_warning" not in described


def test_a_modern_version_does_not_claim_settings_are_missing(
    modern: tuple[ReadSheet, str],
) -> None:
    reader, document_id = modern

    assert "settings_available" not in reader.workbook(document_id)
