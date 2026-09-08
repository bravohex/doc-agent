"""A cached value is not a fresh result, and `display` is not always what Excel shows.

Both are reported as a state so a reader never has to infer either. The classification
mirrors what the renderer actually does, so these cases are the contract.
"""

from __future__ import annotations

import pytest

from doc_agent.domain.cells import describe_cell, display_state, value_state


def _cell(**overrides: object) -> dict[str, object]:
    cell: dict[str, object] = {
        "raw_value": "MOG-001",
        "display": "MOG-001",
        "formula": None,
        "cached_value": None,
        "data_type": "s",
    }
    cell.update(overrides)
    return cell


def test_a_cell_without_a_formula_holds_its_own_value() -> None:
    assert value_state(_cell()) == "literal"


def test_a_formula_with_a_saved_result_is_cached_not_computed() -> None:
    """Present, but as old as the last save: never report it as a computed figure."""

    assert value_state(_cell(formula="=B2*2", cached_value=2469135.782)) == "cached"


def test_a_formula_with_no_saved_result_is_uncalculated() -> None:
    """Nothing was computed, which is not a result of zero and not an empty cell."""

    cell = _cell(formula="=B2*2", cached_value=None, raw_value=None, display="", data_type="f")

    assert value_state(cell) == "uncalculated"
    # The empty display string has to be explained, or it reads as an empty cell.
    assert display_state(cell, "General") == "unavailable"


@pytest.mark.parametrize(
    ("number_format", "data_type", "expected"),
    [
        # Formats the renderer reproduces as the sheet shows them.
        ("General", "s", "exact"),
        ("", "s", "exact"),
        ("@", "s", "exact"),
        ("General", "n", "exact"),
        ("0.0%", "n", "exact"),
        ("0%", "n", "exact"),
        ("General", "b", "exact"),
        ("General", "e", "exact"),
        # Rules the renderer does not apply: separators, currency, fixed decimals.
        ("#,##0.00", "n", "approximate"),
        ('"$"#,##0.00', "n", "approximate"),
        ("0.00E+00", "n", "approximate"),
        ("[Red]0.00;[Blue]-0.00", "n", "approximate"),
    ],
)
def test_display_state_follows_what_the_renderer_can_do(
    number_format: str, data_type: str, expected: str
) -> None:
    assert display_state(_cell(data_type=data_type), number_format) == expected


@pytest.mark.parametrize("number_format", ["dd/mm/yyyy", "yyyy-mm-dd", "General", "hh:mm"])
def test_dates_are_normalized_rather_than_formatted(number_format: str) -> None:
    """The sheet's own date order is not reproduced; ISO-8601 is used deliberately."""

    cell = _cell(data_type="d", raw_value="2026-03-01T00:00:00")

    assert display_state(cell, number_format) == "normalized"


def test_a_percentage_stays_exact_even_though_the_stored_value_differs() -> None:
    """0.125 displayed as 12.5% is the renderer doing the format faithfully."""

    cell = _cell(data_type="n", raw_value=0.125, display="12.5%")

    assert display_state(cell, "0.0%") == "exact"


def test_a_missing_number_format_is_treated_as_plain() -> None:
    assert display_state(_cell(data_type="n"), None) == "exact"


def test_describe_cell_returns_both_states() -> None:
    cell = _cell(formula="=B2*2", cached_value=10, data_type="f")

    assert describe_cell(cell, "#,##0.00") == {
        "value_state": "cached",
        "display_state": "approximate",
    }
