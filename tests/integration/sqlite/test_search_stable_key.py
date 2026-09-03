from __future__ import annotations

from pathlib import Path

from doc_agent.adapters.sqlite.connection import SqliteDatabase
from doc_agent.adapters.sqlite.repository import SqliteRepository
from doc_agent.adapters.sqlite.search_index import SqliteSearchIndex
from doc_agent.domain.models import Block, BlockKind, ExtractedDocument, XlsxLocator


def test_search_supports_exact_stable_key_lookup(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "db.sqlite")
    repo = SqliteRepository(db)
    search = SqliteSearchIndex(db)
    project = repo.create_project("Demo")
    locator = XlsxLocator(sheet="Data", row=2, cell_range="A2:B2")
    block = Block(
        stable_key="xlsx:abc:123", kind=BlockKind.TABLE_ROW, ordinal=2, text="Alpha", source=locator
    )
    doc = ExtractedDocument(logical_name="a.xlsx", media_type="application/xlsx", blocks=[block])
    stored = repo.save_version(project.id, doc, "sha", changes=[])
    search.replace_document(project.id, stored.document_id, stored.version_id, [block])
    results = search.search(project.id, "xlsx:abc:123")
    assert len(results) == 1
    assert results[0].stable_key == "xlsx:abc:123"
