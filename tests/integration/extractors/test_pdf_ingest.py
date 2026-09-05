"""A PDF has to behave like any other source once it is in the store."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from doc_agent.bootstrap import build_container

PAGES: list[dict[str, Any]] = [
    {
        "lines": [
            (72, 720, 11, "PayPay settlement is in scope for the first"),
            (72, 706, 11, "release of the integration."),
        ]
    },
    {"lines": []},
]


def test_pdf_ingest_is_searchable_and_reports_what_it_could_not_read(
    tmp_path: Path, write_pdf: Callable[[Sequence[dict[str, Any]]], bytes]
) -> None:
    source = tmp_path / "report.pdf"
    source.write_bytes(write_pdf(PAGES))
    app = build_container(tmp_path / "home")
    project = app.projects.create("PDF")

    result = app.ingest.execute(project.id, source)

    assert result.status == "created"
    assert [w.code for w in result.warnings] == ["pdf_page_without_text"]

    found = app.search.execute(project.id, "PayPay")
    assert len(found) == 1
    assert found[0].source["kind"] == "pdf"
    assert found[0].source["page_number"] == 1

    block = app.retrieve.block(found[0].block_id)
    assert "PayPay settlement" in str(block["text"])

    blocks = app.repository.current_blocks(result.document_id)
    with sqlite3.connect(tmp_path / "home" / "knowledge.sqlite") as connection:
        pages = {
            str(row[0])
            for row in connection.execute(
                "SELECT stable_key FROM containers WHERE document_id=?", (result.document_id,)
            )
        }
    assert {block.container_key for block in blocks} <= pages


def test_reingesting_the_same_pdf_is_unchanged(
    tmp_path: Path, write_pdf: Callable[[Sequence[dict[str, Any]]], bytes]
) -> None:
    source = tmp_path / "report.pdf"
    source.write_bytes(write_pdf(PAGES))
    app = build_container(tmp_path / "home")
    project = app.projects.create("PDF")
    first = app.ingest.execute(project.id, source)

    second = app.ingest.execute(project.id, source, replace_document_id=first.document_id)

    assert second.status == "unchanged"
    assert second.version_number == first.version_number
