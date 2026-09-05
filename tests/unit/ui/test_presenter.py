from __future__ import annotations

import pytest

from doc_agent.domain.models import Change, DocumentSummary, ExtractionWarning, SearchResult
from doc_agent.interfaces.ui import presenter

XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ({"kind": "xlsx", "sheet": "MOG", "row": 12}, "Sheet MOG · row 12"),
        (
            {"kind": "xlsx", "sheet": "MOG", "row": None, "cell_range": "A4:C4"},
            "Sheet MOG · A4:C4",
        ),
        ({"kind": "pdf", "page_number": 3}, "Page 3"),
        (
            {"kind": "pptx", "slide_number": 2, "shape_name": "Title 1"},
            "Slide 2 · Title 1",
        ),
        (
            {"kind": "docx", "section_path": ["Migration", "Rollback"], "paragraph_index": 4},
            "Migration / Rollback · paragraph 4",
        ),
        (
            {"kind": "docx", "section_path": [], "table_index": 2, "row_index": 5},
            "Document · table 2, row 5",
        ),
        ({"kind": "docx", "section_path": [], "part": "header"}, "Header"),
        ({}, "Unknown source"),
    ],
)
def test_a_locator_is_named_the_way_its_own_format_names_places(
    source: dict[str, object], expected: str
) -> None:
    assert presenter.describe_source(source) == expected


@pytest.mark.parametrize(
    ("count", "expected"), [(0, "~0 tokens"), (999, "~999 tokens"), (1_500, "~1.5k tokens")]
)
def test_token_counts_do_not_overstate_their_precision(count: int, expected: str) -> None:
    assert presenter.describe_tokens(count) == expected


def _result(**overrides: object) -> SearchResult:
    values: dict[str, object] = {
        "block_id": "block-1",
        "stable_key": "key-1",
        "document_id": "doc-1",
        "version_id": "version-1",
        "logical_name": "fitgap.xlsx",
        "kind": "table_row",
        "text": "MOG-001\tPayPay",
        "snippet": "MOG-001 [PayPay]",
        "source": {"kind": "xlsx", "sheet": "MOG", "row": 12},
        "estimated_tokens": 12,
    }
    values.update(overrides)
    return SearchResult(**values)  # type: ignore[arg-type]


def test_a_result_is_rendered_with_its_document_kind_and_place() -> None:
    view = presenter.result_views([_result()])[0]

    assert view.document == "fitgap.xlsx"
    assert view.kind == "table row"
    assert view.locator == "Sheet MOG · row 12"
    assert view.snippet == "MOG-001 [PayPay]"
    assert view.tokens == "~12 tokens"


def test_an_empty_snippet_falls_back_to_the_block_text() -> None:
    view = presenter.result_views([_result(snippet="   ")])[0]

    assert view.snippet == "MOG-001\tPayPay"


def test_the_summary_states_what_retrieving_everything_would_cost() -> None:
    assert presenter.search_summary([]) == "No matches"
    assert presenter.search_summary([_result()]) == "1 match · ~12 tokens if all are retrieved"
    assert "2 matches" in presenter.search_summary([_result(), _result()])


def test_documents_are_labelled_by_format_and_version() -> None:
    document = DocumentSummary(
        id="doc-1",
        project_id="project-1",
        logical_name="fitgap.xlsx",
        media_type=XLSX_MEDIA,
        current_version_number=3,
    )

    view = presenter.document_views([document])[0]

    assert (view.name, view.format_label, view.version_label) == ("fitgap.xlsx", "XLSX", "v3")


def test_unchanged_blocks_are_left_out_of_the_change_list() -> None:
    changes = [
        Change(kind="unchanged", stable_key="a", new_text="same"),
        Change(
            kind="changed_semantic",
            stable_key="b",
            new_text="now this",
            new_source={"kind": "pdf", "page_number": 2},
        ),
    ]

    views = presenter.change_views(changes)

    assert [view.label for view in views] == ["Content changed"]
    assert views[0].locator == "Page 2"
    assert views[0].colour == "warning"


def test_a_warning_states_where_it_happened() -> None:
    warning = ExtractionWarning(
        code="pdf_page_without_text",
        message="Page 3 carries no extractable text.",
        source=None,
    )

    assert presenter.warning_lines([warning]) == ["Page 3 carries no extractable text."]


def test_an_ingest_result_reads_as_a_sentence() -> None:
    assert presenter.ingest_summary("created", 1, 0) == "created · version 1 · no changes"
    assert presenter.ingest_summary("updated", 2, 4) == "updated · version 2 · 4 change(s)"
