"""Spreadsheet-shaped reading: address a range the way a person would.

Retrieval by block answers "where is this text", but auditing a workbook means asking
for ``MOG!B2:D10`` and getting those cells and nothing else. These use cases read the
same stored blocks through a sheet-and-range door, paginated, so a few cells cost a few
cells rather than a whole document.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any, cast

from doc_agent.domain.a1 import CellWindow, InvalidRangeError, column_of, parse_range
from doc_agent.domain.cells import describe_cell
from doc_agent.domain.errors import NotFoundError
from doc_agent.ports.repositories import DocumentRepository, Record, row_cursor

#: What an audit usually needs: the address, what the sheet shows, and the value and
#: formula behind it.
DEFAULT_CELL_FIELDS: tuple[str, ...] = (
    "display",
    "raw_value",
    "formula",
    "cached_value",
    # Included by default because both are easy to over-read: a cached value looks like
    # a result, and a display string looks like what the sheet shows.
    "value_state",
    "display_state",
)

#: Selectable per cell. The first group is meaning, the second is appearance.
VALUE_FIELDS = frozenset(
    {"raw_value", "formula", "cached_value", "data_type", "display", "hyperlink", "comment"}
)
LAYOUT_FIELDS = frozenset({"number_format", "merged_range", "hidden_column"})
#: Derived on read from the stored fields, so they describe old documents too.
STATE_FIELDS = frozenset({"value_state", "display_state"})
CELL_FIELDS = VALUE_FIELDS | LAYOUT_FIELDS | STATE_FIELDS

DEFAULT_ROW_LIMIT = 50
MAX_ROW_LIMIT = 500


def _count(value: Any) -> int | None:
    """Count a recorded list, keeping ``None`` as "not recorded" rather than zero."""

    return len(cast(list[Any], value)) if isinstance(value, list) else None


def _recorded(metadata: dict[str, Any], key: str) -> list[Any] | None:
    """Return a recorded list, or ``None`` when this version never recorded the fact.

    An empty list is a finding -- the sheet has no such rules. A version extracted
    before the fact was captured has no finding at all, and must not be reported as
    though it had none.
    """

    if key not in metadata:
        return None
    value = metadata.get(key)
    return cast(list[Any], value) if isinstance(value, list) else []


def _cells(record: Record, key: str) -> list[dict[str, Any]]:
    """Read one of the parallel cell lists, tolerating a block that has neither."""

    section = record.get(key)
    if not isinstance(section, dict):
        return []
    cells = cast(dict[str, Any], section).get("cells")
    if not isinstance(cells, list):
        return []
    return [cell for cell in cast(list[Any], cells) if isinstance(cell, dict)]


def select_cells(record: Record, window: CellWindow, fields: Sequence[str]) -> list[dict[str, Any]]:
    """Return the row's cells inside the column window, carrying only ``fields``.

    Values and layout are stored as parallel lists built in one pass, so they are paired
    by position; the coordinate comes from the layout side and is always included,
    because a cell without its address cannot be cited or checked.
    """

    values, layout = _cells(record, "payload"), _cells(record, "presentation")
    selected: list[dict[str, Any]] = []
    for index, value_cell in enumerate(values):
        layout_cell = layout[index] if index < len(layout) else {}
        coordinate = str(layout_cell.get("coordinate") or "")
        if not coordinate:
            continue
        try:
            if not window.contains_column(column_of(coordinate)):
                continue
        except InvalidRangeError:
            continue
        cell: dict[str, Any] = {"coordinate": coordinate}
        states = (
            describe_cell(value_cell, layout_cell.get("number_format"))
            if any(field in STATE_FIELDS for field in fields)
            else {}
        )
        for field in fields:
            if field in STATE_FIELDS:
                cell[field] = states[field]
            elif field in VALUE_FIELDS:
                cell[field] = value_cell.get(field)
            elif field in LAYOUT_FIELDS:
                cell[field] = layout_cell.get(field)
        selected.append(cell)
    return selected


def normalize_fields(fields: Iterable[str] | None) -> tuple[str, ...]:
    """Validate requested cell fields, naming the unknown ones rather than ignoring them."""

    if fields is None:
        return DEFAULT_CELL_FIELDS
    requested = tuple(dict.fromkeys(field.strip() for field in fields if field.strip()))
    if not requested:
        return DEFAULT_CELL_FIELDS
    unknown = [field for field in requested if field not in CELL_FIELDS]
    if unknown:
        raise ValueError(
            f"Unknown cell field(s): {', '.join(sorted(unknown))}. "
            f"Available: {', '.join(sorted(CELL_FIELDS))}"
        )
    return requested


class ReadSheet:
    """Read worksheet structure and cell ranges from stored blocks."""

    def __init__(self, repository: DocumentRepository) -> None:
        self.repository = repository

    def sheets(self, document_id: str, *, version_id: str | None = None) -> list[Record]:
        """Describe every sheet: order, visibility, extent, and defined tables."""

        described: list[Record] = []
        for container in self.repository.list_containers(document_id, version_id=version_id):
            raw = container.get("metadata")
            metadata = cast(dict[str, Any], raw) if isinstance(raw, dict) else {}
            state = str(metadata.get("state") or "visible")
            described.append(
                {
                    "sheet": container.get("title"),
                    "ordinal": container.get("ordinal"),
                    "kind": container.get("kind"),
                    "state": state,
                    # openpyxl reports "visible", "hidden" or "veryHidden"; anything not
                    # visible is hidden from a reader, so the plain flag says so.
                    "hidden": state != "visible",
                    "dimension": metadata.get("dimension"),
                    "tables": metadata.get("tables") or [],
                    # What a cell was allowed to contain, and which rules watch it, are
                    # facts the values themselves cannot report.
                    "validations": _recorded(metadata, "validations"),
                    "conditional_formats": _recorded(metadata, "conditional_formats"),
                    "defined_names": _recorded(metadata, "defined_names"),
                }
            )
        return described

    def workbook(self, document_id: str, *, version_id: str | None = None) -> Record:
        """Describe the workbook itself: how it calculates, and what its formulas name.

        The calculation mode is the finding that changes how everything else should be
        read. A workbook set to ``manual`` may carry formula results that its own author
        never recalculated, so ``cached`` values in it are stale by design rather than by
        accident -- which is why that warning is stated here instead of left to be
        joined up from two separate calls.
        """

        metadata = self.repository.get_version_metadata(document_id, version_id=version_id)
        document = self.repository.get_document(document_id)
        raw_calculation = metadata.get("calculation")
        calculation = (
            cast(dict[str, Any], raw_calculation) if isinstance(raw_calculation, dict) else None
        )
        sheets = self.sheets(document_id, version_id=version_id)
        read_version = version_id or document.current_version_id
        described: Record = {
            "document_id": document_id,
            "logical_name": document.logical_name,
            "version_id": read_version,
            "is_current_version": read_version == document.current_version_id,
            "sheet_count": metadata.get("sheet_count", len(sheets)),
            "calculation": calculation,
            "defined_names": _recorded(metadata, "defined_names"),
            "sheets": [
                {
                    "sheet": entry["sheet"],
                    "ordinal": entry["ordinal"],
                    "hidden": entry["hidden"],
                    "dimension": entry["dimension"],
                    "tables": _count(entry["tables"]),
                    "validations": _count(entry["validations"]),
                    "conditional_formats": _count(entry["conditional_formats"]),
                }
                for entry in sheets
            ],
        }
        if calculation and calculation.get("automatic") is False:
            described["cached_value_warning"] = (
                "This workbook calculates manually, so a cached formula result may never "
                "have been recalculated by its author. Treat every cached value as the "
                "last saved value, not a current one."
            )
        if calculation is None:
            # A version extracted before these facts were captured has no answer, which
            # is not the same as a workbook with no settings. Null fields say "unknown";
            # this says why, and what to do about it.
            described["settings_available"] = False
            described["settings_note"] = (
                "This version was extracted before workbook settings were captured, so "
                "calculation mode, defined names, and validation rules are unknown "
                "rather than absent. Re-ingest the source file to record them."
            )
        return described

    def range(
        self,
        document_id: str,
        sheet: str,
        reference: str | None = None,
        *,
        fields: Iterable[str] | None = None,
        version_id: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
    ) -> Record:
        """Return the cells of ``sheet`` inside ``reference``, one page at a time.

        A missing sheet names the sheets that do exist: an empty page would otherwise be
        indistinguishable from a typo in the sheet name.
        """

        available = [
            str(entry["sheet"]) for entry in self.sheets(document_id, version_id=version_id)
        ]
        if sheet not in available:
            match = [name for name in available if name.casefold() == sheet.casefold()]
            if not match:
                raise NotFoundError(
                    f"Sheet not found: {sheet!r}. This document has: {', '.join(available) or 'none'}"
                )
            sheet = match[0]

        window = parse_range(reference, sheet=sheet) if reference else parse_range("A1:XFD1048576")
        selected_fields = normalize_fields(fields)
        page_size = DEFAULT_ROW_LIMIT if limit is None else max(1, min(limit, MAX_ROW_LIMIT))

        records = self.repository.get_sheet_rows(
            document_id,
            sheet,
            min_row=window.min_row,
            max_row=window.max_row,
            version_id=version_id,
            after=cursor,
            # One extra row reveals whether another page exists without a second query.
            limit=page_size + 1,
        )
        has_more = len(records) > page_size
        page = records[:page_size]

        rows: list[Record] = []
        for record in page:
            source = record.get("source")
            located = cast(dict[str, Any], source) if isinstance(source, dict) else {}
            rows.append(
                {
                    "row": located.get("row"),
                    "ordinal": record.get("ordinal"),
                    "block_id": record.get("block_id"),
                    "cells": select_cells(record, window, selected_fields),
                }
            )
        document = self.repository.get_document(document_id)
        # The version actually read, taken from the rows themselves: reporting the
        # document's current version would misdescribe a pinned or cursor-continued read
        # as soon as the document was re-ingested.
        read_version = (
            str(page[0]["version_id"]) if page else (version_id or document.current_version_id)
        )
        return {
            "document_id": document_id,
            "logical_name": document.logical_name,
            "version_id": read_version,
            # Says whether this page is the document as it stands now, so a caller can
            # notice reading history without having to compare ids themselves.
            "is_current_version": read_version == document.current_version_id,
            "sheet": sheet,
            "range": window.label,
            "fields": list(selected_fields),
            "rows": rows,
            "next_cursor": row_cursor(page[-1]) if has_more and page else None,
        }
