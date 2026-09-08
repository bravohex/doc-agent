"""A1 notation is what a spreadsheet user types, so every accepted spelling is pinned
and every ambiguous one is refused rather than guessed at.
"""

from __future__ import annotations

import pytest

from doc_agent.domain.a1 import (
    MAX_COLUMN,
    MAX_ROW,
    CellWindow,
    InvalidRangeError,
    column_index,
    column_letter,
    column_of,
    parse_range,
)


@pytest.mark.parametrize(
    ("letters", "index"),
    [("A", 1), ("B", 2), ("Z", 26), ("AA", 27), ("AB", 28), ("AZ", 52), ("BA", 53), ("ZZ", 702)],
)
def test_column_letters_and_indexes_round_trip(letters: str, index: int) -> None:
    assert column_index(letters) == index
    assert column_letter(index) == letters


def test_column_index_is_case_insensitive() -> None:
    assert column_index("ab") == column_index("AB")


@pytest.mark.parametrize("coordinate", ["B2", "$B$2", "b2", "AB120"])
def test_column_of_reads_a_coordinate(coordinate: str) -> None:
    assert column_of(coordinate) == column_index(coordinate.replace("$", "").rstrip("0123456789"))


@pytest.mark.parametrize(
    ("reference", "expected"),
    [
        ("B2", CellWindow(2, 2, 2, 2)),
        ("B2:D10", CellWindow(2, 2, 4, 10)),
        # Corners in any order describe the same rectangle.
        ("D10:B2", CellWindow(2, 2, 4, 10)),
        ("$B$2:$D$10", CellWindow(2, 2, 4, 10)),
        ("b2:d10", CellWindow(2, 2, 4, 10)),
        # Whole columns and whole rows are ordinary spellings, not errors.
        ("B:D", CellWindow(2, 1, 4, MAX_ROW)),
        ("2:10", CellWindow(1, 2, MAX_COLUMN, 10)),
        ("B", CellWindow(2, 1, 2, MAX_ROW)),
        ("7", CellWindow(1, 7, MAX_COLUMN, 7)),
    ],
)
def test_parse_range_reads_every_accepted_spelling(reference: str, expected: CellWindow) -> None:
    assert parse_range(reference) == expected


def test_a_sheet_prefix_is_accepted_and_checked() -> None:
    assert parse_range("MOG!B2:D10", sheet="MOG") == CellWindow(2, 2, 4, 10)
    assert parse_range("'My Sheet'!B2", sheet="My Sheet") == CellWindow(2, 2, 2, 2)
    # Silently reading a different sheet than the caller named would be worse than failing.
    with pytest.raises(InvalidRangeError, match="names sheet"):
        parse_range("Other!B2:D10", sheet="MOG")


@pytest.mark.parametrize("reference", ["B2:D", "D:B2", "2:B10"])
def test_a_half_named_axis_is_refused(reference: str) -> None:
    with pytest.raises(InvalidRangeError, match="only one side"):
        parse_range(reference)


@pytest.mark.parametrize("reference", ["", "   ", "??", "B2:", ":D10", "1B", "B2D10"])
def test_nonsense_is_refused(reference: str) -> None:
    with pytest.raises(InvalidRangeError):
        parse_range(reference)


def test_a_column_beyond_the_sheet_limit_is_refused() -> None:
    with pytest.raises(InvalidRangeError, match="beyond the sheet limit"):
        column_index("XFE")


def test_window_membership_and_label() -> None:
    window = parse_range("B2:D10")

    assert window.contains_column(3)
    assert not window.contains_column(5)
    assert window.contains_row(10)
    assert not window.contains_row(11)
    assert window.label == "B2:D10"
    assert parse_range("B2").label == "B2"
