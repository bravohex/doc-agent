"""What a cell's value and rendering can actually be trusted to mean.

Two things about a spreadsheet cell are easy to over-read. A cached value looks like a
result but is only what the application that last saved the file wrote there. A display
string looks like what the sheet shows but is produced here, from the stored value and
the number format, and the renderer does not implement every Excel formatting rule.

Both are reported as an explicit state rather than left for a reader to assume. The
states are derived from stored fields, so they describe documents extracted before these
states existed just as well as new ones.
"""

from __future__ import annotations

from typing import Any, Literal

type ValueState = Literal["literal", "cached", "uncalculated"]
type DisplayState = Literal["exact", "normalized", "approximate", "unavailable"]

#: Formats the renderer reproduces as the sheet shows them: no formatting at all, or
#: text. Anything else carries rules -- separators, currency, padding, date order --
#: that it does not apply.
_PLAIN_FORMATS = frozenset({"general", "@", ""})


def value_state(cell: dict[str, Any]) -> ValueState:
    """Say where a cell's value came from.

    ``literal``      the value is stored in the cell; nothing was computed.
    ``cached``       a formula's last saved result. Real, but as old as the last save,
                     and no evidence that it was recalculated. Never present it as a
                     freshly computed figure.
    ``uncalculated`` the cell holds a formula and the file carries no result for it.
                     Nothing was computed, which is not the same as a result of zero or
                     an empty cell.
    """

    if not cell.get("formula"):
        return "literal"
    return "cached" if cell.get("cached_value") is not None else "uncalculated"


def display_state(cell: dict[str, Any], number_format: str | None) -> DisplayState:
    """Say how far ``display`` can be trusted against what the sheet shows.

    ``exact``       the format is one this renderer reproduces: plain or text formats,
                    percentages, booleans, and error text.
    ``normalized``  deliberately canonical rather than the sheet's own format: dates and
                    times are rendered ISO-8601, not ``dd/mm/yyyy``.
    ``approximate`` the format carries rules that are not applied -- thousands
                    separators, currency, fixed decimals, scientific, custom. Read
                    ``raw_value`` with ``number_format`` and render it yourself.
    ``unavailable`` there is no value to display, because the formula was never
                    calculated. The empty string means "not computed", not "empty".
    """

    if value_state(cell) == "uncalculated":
        return "unavailable"
    data_type = str(cell.get("data_type") or "")
    fmt = (number_format or "").strip().casefold()

    if data_type == "d":
        return "normalized"
    if data_type == "b" or data_type == "e":
        return "exact"
    if "%" in fmt:
        # The renderer applies the percent scale and the format's own decimal count.
        return "exact"
    if fmt in _PLAIN_FORMATS:
        return "exact"
    return "approximate"


def describe_cell(cell: dict[str, Any], number_format: str | None) -> dict[str, str]:
    """Return both states for one cell, ready to attach to a retrieval record."""

    return {
        "value_state": value_state(cell),
        "display_state": display_state(cell, number_format),
    }
