"""Replacing a document must not collide with another document's logical name."""

from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook

from doc_agent.bootstrap import build_container
from doc_agent.domain.errors import VersionConflictError


def _workbook(path: Path, value: str) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["ID", "Name"])
    sheet.append(["1", value])
    workbook.save(path)


def test_replacing_onto_a_taken_name_raises_a_version_conflict(tmp_path: Path) -> None:
    app = build_container(tmp_path / "home")
    project = app.projects.create("Conflicts")
    first = tmp_path / "a.xlsx"
    second = tmp_path / "b.xlsx"
    _workbook(first, "Alpha")
    _workbook(second, "Beta")
    original = app.ingest.execute(project.id, first)
    app.ingest.execute(project.id, second)

    with pytest.raises(VersionConflictError, match="already has a document named b.xlsx"):
        app.ingest.execute(project.id, second, replace_document_id=original.document_id)

    # The rejected replacement must leave both documents exactly as they were.
    assert {d.logical_name for d in app.repository.list_documents(project.id)} == {
        "a.xlsx",
        "b.xlsx",
    }
    assert app.repository.get_document(original.document_id).current_version_number == 1


def test_replacing_with_a_new_unused_name_is_allowed(tmp_path: Path) -> None:
    app = build_container(tmp_path / "home")
    project = app.projects.create("Renames")
    first = tmp_path / "a.xlsx"
    renamed = tmp_path / "c.xlsx"
    _workbook(first, "Alpha")
    _workbook(renamed, "Gamma")
    original = app.ingest.execute(project.id, first)

    result = app.ingest.execute(project.id, renamed, replace_document_id=original.document_id)

    assert result.document_id == original.document_id
    assert result.version_number == 2
    assert app.repository.get_document(original.document_id).logical_name == "c.xlsx"
