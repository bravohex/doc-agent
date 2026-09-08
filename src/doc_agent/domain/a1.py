"""A1 notation, the way a spreadsheet user writes an address.

Parsing lives in the domain because it is about spreadsheets, not about storage, and it
deliberately depends on no Office library: a caller naming ``B2:D10`` must get the same
window whatever read the file.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_CELL = re.compile(r"^(?P<column>[A-Z]{1,3})?(?P<row>[1-9][0-9]{0,6})?$")

#: Excel's own ceilings. A window is clamped to them so an open-ended side such as
#: ``B:B`` stays a finite range instead of an unbounded scan.
MAX_ROW = 1_048_576
MAX_COLUMN = 16_384


class InvalidRangeError(ValueError):
    """Raised when a range cannot be read as A1 notation."""


@dataclass(frozen=True, slots=True)
class CellWindow:
    """An inclusive rectangle of columns and rows."""

    min_column: int
    min_row: int
    max_column: int
    max_row: int

    def contains_column(self, column: int) -> bool:
        return self.min_column <= column <= self.max_column

    def contains_row(self, row: int) -> bool:
        return self.min_row <= row <= self.max_row

    @property
    def label(self) -> str:
        """Render the window back as A1, for echoing what was actually read."""

        start = f"{column_letter(self.min_column)}{self.min_row}"
        end = f"{column_letter(self.max_column)}{self.max_row}"
        return start if start == end else f"{start}:{end}"


def column_index(letters: str) -> int:
    """Convert column letters to a 1-based index: ``A`` is 1, ``AA`` is 27."""

    text = letters.strip().upper()
    if not text or not text.isalpha():
        raise InvalidRangeError(f"Not a column reference: {letters!r}")
    index = 0
    for character in text:
        index = index * 26 + (ord(character) - ord("A") + 1)
    if index > MAX_COLUMN:
        raise InvalidRangeError(f"Column beyond the sheet limit: {letters!r}")
    return index


def column_letter(index: int) -> str:
    """Convert a 1-based column index back to letters."""

    if index < 1:
        raise InvalidRangeError(f"Column index must be positive: {index}")
    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(ord("A") + remainder) + letters
    return letters


def column_of(coordinate: str) -> int:
    """Return the column index of a cell coordinate such as ``AB12``."""

    match = re.match(r"^\$?([A-Za-z]{1,3})\$?[0-9]{1,7}$", coordinate.strip())
    if not match:
        raise InvalidRangeError(f"Not a cell coordinate: {coordinate!r}")
    return column_index(match.group(1))


def parse_range(reference: str, *, sheet: str | None = None) -> CellWindow:
    """Read ``B2``, ``B2:D10``, ``B:D`` or ``2:10`` into a finite window.

    An open side is filled with the sheet's limit rather than rejected, because
    ``B:B`` is how a whole column is normally written. Corners may arrive in any
    order, so ``D10:B2`` describes the same rectangle as ``B2:D10``.
    """

    text = reference.strip().replace("$", "")
    if not text:
        raise InvalidRangeError("Range is empty")
    if "!" in text:
        prefix, _, text = text.rpartition("!")
        named = prefix.strip().strip("'")
        if sheet is not None and named and named.casefold() != sheet.casefold():
            raise InvalidRangeError(
                f"Range names sheet {named!r} but sheet {sheet!r} was requested"
            )
    start_text, separator, end_text = text.partition(":")
    start = _parse_corner(start_text)
    end = _parse_corner(end_text) if separator else start
    columns = [corner[0] for corner in (start, end) if corner[0] is not None]
    rows = [corner[1] for corner in (start, end) if corner[1] is not None]
    # Each axis is named by both corners or by neither. One corner alone -- "B2:D" --
    # has no rectangle it could mean, so it is refused instead of guessed at.
    if len(columns) == 1 or len(rows) == 1:
        raise InvalidRangeError(
            f"Range names an axis on only one side: {reference!r}. "
            "Write both corners (B2:D10), whole columns (B:D), or whole rows (2:10)."
        )
    minimum_column, maximum_column = (min(columns), max(columns)) if columns else (1, MAX_COLUMN)
    minimum_row, maximum_row = (min(rows), max(rows)) if rows else (1, MAX_ROW)
    return CellWindow(
        min_column=minimum_column,
        min_row=minimum_row,
        max_column=maximum_column,
        max_row=maximum_row,
    )


def _parse_corner(text: str) -> tuple[int | None, int | None]:
    """Read one side of a range into its column and row, either of which may be absent."""

    match = _CELL.match(text.strip().upper())
    if match is None or not text.strip():
        raise InvalidRangeError(f"Not an A1 reference: {text!r}")
    letters, digits = match.group("column"), match.group("row")
    if letters is None and digits is None:
        raise InvalidRangeError(f"Not an A1 reference: {text!r}")
    return (
        column_index(letters) if letters else None,
        int(digits) if digits else None,
    )
