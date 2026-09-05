"""Distinct documents must not overwrite each other's exported table file."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from doc_agent.bootstrap import build_container


def _workbook(path: Path, value: str) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["ID", "Name"])
    sheet.append(["1", value])
    workbook.save(path)


def test_documents_sanitizing_to_one_name_export_separate_tables(tmp_path: Path) -> None:
    app = build_container(tmp_path / "home")
    project = app.projects.create("Collision")
    first = tmp_path / "fit gap.xlsx"
    second = tmp_path / "fit_gap.xlsx"
    _workbook(first, "Alpha")
    _workbook(second, "Beta")
    app.ingest.execute(project.id, first)
    app.ingest.execute(project.id, second)

    destination = tmp_path / "out"
    app.export.execute(project.id, destination)

    tables = sorted((destination / "tables").glob("*.tsv"))
    assert len(tables) == 2
    exported = "".join(table.read_text(encoding="utf-8") for table in tables)
    assert "Alpha" in exported and "Beta" in exported
