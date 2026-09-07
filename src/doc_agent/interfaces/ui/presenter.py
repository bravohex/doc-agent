"""Turn stored records into display-ready values.

Kept free of NiceGUI so the wording, labelling and counting the interface shows can be
tested directly, and so the page code stays declarative wiring.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from doc_agent.domain.models import Change, DocumentSummary, ExtractionWarning, SearchResult

_FORMAT_LABELS = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "XLSX",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "DOCX",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "PPTX",
    "application/pdf": "PDF",
}

_CHANGE_LABELS: dict[str, tuple[str, str]] = {
    "added": ("Added", "positive"),
    "deleted": ("Removed", "negative"),
    "changed_semantic": ("Content changed", "warning"),
    "changed_presentation": ("Formatting changed", "info"),
    "moved": ("Moved", "info"),
    "unchanged": ("Unchanged", "grey"),
}


@dataclass(frozen=True, slots=True)
class ResultView:
    """One search hit, ready to render."""

    block_id: str
    document: str
    kind: str
    locator: str
    snippet: str
    tokens: str
    needs_visual: bool


@dataclass(frozen=True, slots=True)
class DocumentView:
    document_id: str
    name: str
    format_label: str
    version_label: str
    active: bool
    retrieval_label: str


@dataclass(frozen=True, slots=True)
class ChangeView:
    label: str
    colour: str
    locator: str
    text: str


def describe_source(source: dict[str, Any]) -> str:
    """Name the place a block came from the way its own format names places."""

    kind = str(source.get("kind", ""))
    if kind == "xlsx":
        return " · ".join(_present(f"Sheet {source.get('sheet')}", _row(source)))
    if kind == "pptx":
        shape = source.get("shape_name") or source.get("shape_id")
        return " · ".join(
            _present(f"Slide {source.get('slide_number')}", shape and f"{shape}", _row(source))
        )
    if kind == "pdf":
        return " · ".join(_present(f"Page {source.get('page_number')}", _row(source)))
    if kind == "docx":
        path = " / ".join(str(part) for part in source.get("section_path") or ())
        part = str(source.get("part") or "document")
        where = path or (part.capitalize() if part != "document" else "Document")
        table = source.get("table_index")
        detail = f"table {table}, row {source.get('row_index')}" if table else _paragraph(source)
        return " · ".join(_present(where, detail))
    return "Unknown source"


def describe_format(media_type: str) -> str:
    return _FORMAT_LABELS.get(media_type, "Document")


def describe_tokens(count: int) -> str:
    """Round large counts, because an exact estimate would overstate its own precision."""

    if count >= 1_000:
        return f"~{count / 1_000:.1f}k tokens"
    return f"~{count} tokens"


def result_views(results: Sequence[SearchResult]) -> list[ResultView]:
    return [
        ResultView(
            block_id=result.block_id,
            document=result.logical_name,
            kind=result.kind.replace("_", " "),
            locator=describe_source(result.source),
            snippet=result.snippet.strip() or result.text[:240],
            tokens=describe_tokens(result.estimated_tokens),
            needs_visual=result.visual_required,
        )
        for result in results
    ]


def search_summary(results: Sequence[SearchResult]) -> str:
    if not results:
        return "No matches"
    total = sum(result.estimated_tokens for result in results)
    noun = "match" if len(results) == 1 else "matches"
    return f"{len(results)} {noun} · {describe_tokens(total)} if all are retrieved"


def document_views(documents: Sequence[DocumentSummary]) -> list[DocumentView]:
    return [
        DocumentView(
            document_id=document.id,
            name=document.logical_name,
            format_label=describe_format(document.media_type),
            version_label=f"v{document.current_version_number}",
            active=document.active,
            # A paused document still fills a row in the library, so the row itself has
            # to say why searches never return it.
            retrieval_label="" if document.active else "Paused · excluded from retrieval",
        )
        for document in documents
    ]


def change_views(changes: Sequence[Change]) -> list[ChangeView]:
    """Order changes so that what actually differs is read before what stayed put."""

    views = [
        ChangeView(
            label=_CHANGE_LABELS.get(change.kind, (change.kind, "grey"))[0],
            colour=_CHANGE_LABELS.get(change.kind, (change.kind, "grey"))[1],
            locator=describe_source(change.new_source or change.old_source or {}),
            text=(change.new_text or change.old_text or "").strip(),
        )
        for change in changes
        if change.kind != "unchanged"
    ]
    return sorted(views, key=lambda view: view.label)


def ingest_summary(status: str, version_number: int, change_count: int) -> str:
    changes = "no changes" if change_count == 0 else f"{change_count} change(s)"
    return f"{status} · version {version_number} · {changes}"


def warning_lines(warnings: Sequence[ExtractionWarning]) -> list[str]:
    return [
        f"{describe_source(warning.source.model_dump(mode='json'))}: {warning.message}"
        if warning.source
        else warning.message
        for warning in warnings
    ]


def _present(*parts: object) -> list[str]:
    return [str(part) for part in parts if part]


def _row(source: dict[str, Any]) -> str | None:
    row = source.get("row") or source.get("row_index")
    if row:
        return f"row {row}"
    cell_range = source.get("cell_range")
    return str(cell_range) if cell_range else None


def _paragraph(source: dict[str, Any]) -> str | None:
    index = source.get("paragraph_index")
    return f"paragraph {index}" if index else None
