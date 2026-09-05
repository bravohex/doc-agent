"""Moving or restyling content must not be reported as a change in what it says."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

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


PDF_BODY = [(72, 720, 11, "PayPay settlement is in scope.")]
COVER = [(72, 720, 16, "Cover"), (72, 690, 11, "Prepared for the steering committee.")]


def test_text_pushed_onto_a_later_pdf_page_moves_rather_than_disappearing(
    tmp_path: Path, write_pdf: Callable[[Sequence[dict[str, Any]]], bytes]
) -> None:
    source = tmp_path / "report.pdf"
    source.write_bytes(write_pdf([{"lines": PDF_BODY}]))
    app = build_container(tmp_path / "home")
    project = app.projects.create("Reflow")
    first = app.ingest.execute(project.id, source)

    # A cover page is added, so the body now sits on page 2.
    source.write_bytes(write_pdf([{"lines": COVER}, {"lines": PDF_BODY}]))
    second = app.ingest.execute(project.id, source, replace_document_id=first.document_id)

    kinds = {change.new_text: change.kind for change in second.diff.changes}
    assert kinds["PayPay settlement is in scope."] == "moved"
    assert not [change for change in second.diff.changes if change.kind == "changed_semantic"]

    moved = next(
        block
        for block in app.repository.current_blocks(first.document_id)
        if "PayPay" in block.text
    )
    assert moved.source.page_number == 2
