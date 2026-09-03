from __future__ import annotations

from pathlib import Path

from doc_agent.adapters.sqlite.connection import SqliteDatabase
from doc_agent.adapters.sqlite.repository import SqliteRepository
from doc_agent.adapters.sqlite.search_index import SqliteSearchIndex
from doc_agent.domain.models import Block, BlockKind, Container, ExtractedDocument, XlsxLocator


def _document(text: str, classification: str = "A") -> ExtractedDocument:
    locator = XlsxLocator(sheet="MOG", row=2, cell_range="A2:C2")
    block = Block(
        stable_key="xlsx:mog:mog-001",
        kind=BlockKind.TABLE_ROW,
        ordinal=2,
        text=text,
        source=locator,
        payload={"cells": ["MOG-001", "PayPay", classification]},
    )
    return ExtractedDocument(
        logical_name="fitgap.xlsx",
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        containers=[
            Container(
                stable_key="xlsx:mog", kind="worksheet", title="MOG", ordinal=1, source=locator
            )
        ],
        blocks=[block],
    )


def test_repository_versions_and_current_fts_search(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "knowledge.sqlite")
    repo = SqliteRepository(db)
    search = SqliteSearchIndex(db)
    project = repo.create_project("OLM")
    first = repo.save_version(project.id, _document("MOG-001 PayPay A"), "sha1", changes=[])
    search.replace_document(
        project.id, first.document_id, first.version_id, _document("MOG-001 PayPay A").blocks
    )
    results = search.search(project.id, "PayPay")
    assert results and results[0].source["sheet"] == "MOG"
    second = repo.save_version(project.id, _document("MOG-001 PayPay C", "C"), "sha2", changes=[])
    search.replace_document(
        project.id, second.document_id, second.version_id, _document("MOG-001 PayPay C", "C").blocks
    )
    assert search.search(project.id, "PayPay")[0].text.endswith("C")
    assert len(repo.history(second.document_id)) == 2
