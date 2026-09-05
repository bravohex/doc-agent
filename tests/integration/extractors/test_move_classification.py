"""Moving or restyling content must not be reported as a change in what it says."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from doc_agent.bootstrap import build_container


def _workbook(path: Path, rows: list[list[str]], *, hidden_row: int | None = None) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "MOG"
    for row in rows:
        sheet.append(row)
    if hidden_row is not None:
        sheet.row_dimensions[hidden_row].hidden = True
    workbook.save(path)


ROWS = [["ID", "Name"], ["MOG-1", "Alpha"], ["MOG-2", "Beta"]]
ROWS_WITH_INSERT = [["ID", "Name"], ["MOG-0", "Zero"], ["MOG-1", "Alpha"], ["MOG-2", "Beta"]]


def test_inserting_a_row_above_moves_the_rows_below(tmp_path: Path) -> None:
    source = tmp_path / "book.xlsx"
    _workbook(source, ROWS)
    app = build_container(tmp_path / "home")
    project = app.projects.create("Moves")
    first = app.ingest.execute(project.id, source)

    _workbook(source, ROWS_WITH_INSERT)
    second = app.ingest.execute(project.id, source, replace_document_id=first.document_id)

    kinds = {change.new_text: change.kind for change in second.diff.changes}
    assert kinds["MOG-0\tZero"] == "added"
    assert kinds["MOG-1\tAlpha"] == "moved"
    assert kinds["MOG-2\tBeta"] == "moved"
    assert not [change for change in second.diff.changes if change.kind == "changed_semantic"]


def test_hiding_a_row_is_a_presentation_change(tmp_path: Path) -> None:
    source = tmp_path / "book.xlsx"
    _workbook(source, ROWS)
    app = build_container(tmp_path / "home")
    project = app.projects.create("Styling")
    first = app.ingest.execute(project.id, source)

    _workbook(source, ROWS, hidden_row=2)
    second = app.ingest.execute(project.id, source, replace_document_id=first.document_id)

    assert {change.kind for change in second.diff.changed} == {"changed_presentation"}
