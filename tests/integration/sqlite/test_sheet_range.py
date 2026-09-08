"""Reading a workbook by sheet and range, instead of by block.

The point is cost: asking for three cells must not load a sheet. These tests run against
real stored blocks so the SQL filtering and the column slicing are both exercised.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from doc_agent.adapters.sqlite.connection import SqliteDatabase
from doc_agent.adapters.sqlite.repository import SqliteRepository
from doc_agent.application.sheets import ReadSheet
from doc_agent.domain.a1 import InvalidRangeError
from doc_agent.domain.errors import NotFoundError
from doc_agent.domain.models import (
    Block,
    BlockKind,
    Container,
    ExtractedDocument,
    XlsxLocator,
)
from doc_agent.ports.repositories import row_cursor

COLUMNS = ("A", "B", "C", "D")


def _row_block(sheet: str, row: int) -> Block:
    """A row shaped the way the XLSX extractor shapes one: parallel value/layout lists."""

    return Block(
        stable_key=f"{sheet}-row-{row}",
        kind=BlockKind.TABLE_ROW,
        ordinal=row,
        text="\t".join(f"{letter}{row}" for letter in COLUMNS),
        source=XlsxLocator(sheet=sheet, row=row, cell_range=f"A{row}:D{row}"),
        payload={
            "cells": [
                {
                    "raw_value": f"{letter}{row}",
                    "display": f"{letter}{row}",
                    "formula": f"={letter}{row}*2" if letter == "C" else None,
                    "cached_value": 42 if letter == "C" else None,
                    "data_type": "s",
                    "hyperlink": None,
                    "comment": None,
                }
                for letter in COLUMNS
            ]
        },
        presentation={
            "cells": [
                {
                    "coordinate": f"{letter}{row}",
                    "number_format": "0.0%" if letter == "D" else "General",
                    "merged_range": None,
                    "hidden_column": False,
                }
                for letter in COLUMNS
            ]
        },
    )


def _workbook() -> ExtractedDocument:
    return ExtractedDocument(
        logical_name="big.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        containers=[
            Container(
                stable_key="sheet-mog",
                kind="worksheet",
                title="MOG",
                ordinal=1,
                source=XlsxLocator(sheet="MOG", row=1, cell_range="A1:D10"),
                metadata={
                    "state": "visible",
                    "dimension": "A1:D10",
                    "tables": [{"name": "FitGap", "ref": "A1:D10"}],
                },
            ),
            Container(
                stable_key="sheet-internal",
                kind="worksheet",
                title="Internal",
                ordinal=2,
                source=XlsxLocator(sheet="Internal", row=1, cell_range="A1:B1"),
                metadata={"state": "hidden", "dimension": "A1:B1", "tables": []},
            ),
        ],
        blocks=[_row_block("MOG", row) for row in range(1, 11)] + [_row_block("Internal", 1)],
    )


@pytest.fixture
def reader(tmp_path: Path) -> tuple[ReadSheet, str]:
    repository = SqliteRepository(SqliteDatabase(tmp_path / "knowledge.sqlite"))
    project = repository.create_project("Audit")
    stored = repository.save_version(project.id, _workbook(), "sha", changes=[])
    return ReadSheet(repository), stored.document_id


def test_sheets_report_order_visibility_extent_and_tables(reader: tuple[ReadSheet, str]) -> None:
    sheet_reader, document_id = reader

    described = sheet_reader.sheets(document_id)

    assert [(s["sheet"], s["ordinal"], s["hidden"]) for s in described] == [
        ("MOG", 1, False),
        ("Internal", 2, True),
    ]
    assert described[0]["dimension"] == "A1:D10"
    assert described[0]["tables"] == [{"name": "FitGap", "ref": "A1:D10"}]
    # "hidden" and "veryHidden" both mean hidden to a reader, so the raw state is kept too.
    assert described[1]["state"] == "hidden"


def test_a_range_returns_only_the_cells_inside_it(reader: tuple[ReadSheet, str]) -> None:
    sheet_reader, document_id = reader

    page = sheet_reader.range(document_id, "MOG", "B2:C4")

    assert page["sheet"] == "MOG"
    assert page["range"] == "B2:C4"
    assert [row["row"] for row in page["rows"]] == [2, 3, 4]
    for row in page["rows"]:
        assert [cell["coordinate"] for cell in row["cells"]] == [
            f"B{row['row']}",
            f"C{row['row']}",
        ]


def test_only_the_requested_sheet_is_read(reader: tuple[ReadSheet, str]) -> None:
    sheet_reader, document_id = reader

    page = sheet_reader.range(document_id, "Internal")

    assert [row["row"] for row in page["rows"]] == [1]
    assert page["rows"][0]["cells"][0]["coordinate"] == "A1"


def test_fields_select_what_each_cell_carries(reader: tuple[ReadSheet, str]) -> None:
    sheet_reader, document_id = reader

    page = sheet_reader.range(
        document_id, "MOG", "C2", fields=["formula", "cached_value", "number_format"]
    )
    cell = page["rows"][0]["cells"][0]

    # The coordinate is never optional: a cell without its address cannot be cited.
    assert set(cell) == {"coordinate", "formula", "cached_value", "number_format"}
    assert cell["formula"] == "=C2*2"
    assert cell["cached_value"] == 42
    assert page["fields"] == ["formula", "cached_value", "number_format"]


def test_an_unknown_field_is_named_rather_than_ignored(reader: tuple[ReadSheet, str]) -> None:
    sheet_reader, document_id = reader

    with pytest.raises(ValueError, match="Unknown cell field"):
        sheet_reader.range(document_id, "MOG", "A1", fields=["formulaa"])


def test_paging_covers_every_row_exactly_once(reader: tuple[ReadSheet, str]) -> None:
    sheet_reader, document_id = reader
    seen: list[int] = []
    cursor: str | None = None
    pages = 0

    while True:
        page = sheet_reader.range(document_id, "MOG", limit=3, cursor=cursor)
        seen += [int(row["row"]) for row in page["rows"]]
        pages += 1
        cursor = page["next_cursor"]
        if cursor is None:
            break
        assert pages < 10, "paging did not terminate"

    assert seen == list(range(1, 11))
    assert pages == 4


def test_the_last_page_reports_no_cursor(reader: tuple[ReadSheet, str]) -> None:
    sheet_reader, document_id = reader

    page = sheet_reader.range(document_id, "MOG", limit=50)

    assert len(page["rows"]) == 10
    assert page["next_cursor"] is None


def test_the_version_read_is_reported(reader: tuple[ReadSheet, str]) -> None:
    """Two pages can then be checked for coming from the same state of the document."""

    sheet_reader, document_id = reader

    first = sheet_reader.range(document_id, "MOG", limit=3)
    second = sheet_reader.range(document_id, "MOG", limit=3, cursor=first["next_cursor"])

    assert first["version_id"] == second["version_id"]
    assert first["version_id"]


def test_a_missing_sheet_names_the_sheets_that_exist(reader: tuple[ReadSheet, str]) -> None:
    sheet_reader, document_id = reader

    with pytest.raises(NotFoundError, match=re.escape("MOG, Internal")):
        sheet_reader.range(document_id, "Summary", "A1")


def test_a_sheet_name_matches_regardless_of_case(reader: tuple[ReadSheet, str]) -> None:
    sheet_reader, document_id = reader

    assert sheet_reader.range(document_id, "mog", "A1")["sheet"] == "MOG"


def test_an_ambiguous_range_is_refused(reader: tuple[ReadSheet, str]) -> None:
    sheet_reader, document_id = reader

    with pytest.raises(InvalidRangeError):
        sheet_reader.range(document_id, "MOG", "B2:D")


def test_paging_table_rows_never_skips_a_repeated_ordinal(tmp_path: Path) -> None:
    """`ordinal` restarts on every sheet, so it cannot be a page boundary by itself.

    On a three-sheet workbook, paging one row at a time on ordinal alone lost every row
    whose ordinal an earlier sheet had already used.
    """

    repository = SqliteRepository(SqliteDatabase(tmp_path / "knowledge.sqlite"))
    project = repository.create_project("Audit")
    stored = repository.save_version(project.id, _workbook(), "sha", changes=[])
    document_id = stored.document_id
    everything = repository.get_table_rows(document_id)
    repeated = {int(row["ordinal"]) for row in everything}
    assert len(repeated) < len(everything), "the fixture no longer repeats an ordinal"

    seen: list[str] = []
    cursor: str | None = None
    while True:
        page = repository.get_table_rows(document_id, after=cursor, limit=1)
        if not page:
            break
        seen.append(str(page[0]["stable_key"]))
        cursor = row_cursor(page[0])
        assert len(seen) <= len(everything) + 1, "paging did not terminate"

    assert sorted(seen) == sorted(str(row["stable_key"]) for row in everything)
    assert len(seen) == len(set(seen)), "a row was returned twice"


def test_a_cursor_this_api_did_not_produce_is_refused(tmp_path: Path) -> None:
    repository = SqliteRepository(SqliteDatabase(tmp_path / "knowledge.sqlite"))
    project = repository.create_project("Audit")
    stored = repository.save_version(project.id, _workbook(), "sha", changes=[])

    with pytest.raises(ValueError, match="page boundary"):
        repository.get_table_rows(stored.document_id, after="not-a-cursor")
