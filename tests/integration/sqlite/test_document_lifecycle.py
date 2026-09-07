"""Pausing withholds a document's content while keeping it; deleting removes it.

The visual cases matter most: content is stored once no matter how many documents embed
it, so deleting one document must not blank an image another still shows.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from doc_agent.adapters.filesystem.visual_store import FileVisualStore
from doc_agent.adapters.sqlite.connection import SqliteDatabase
from doc_agent.adapters.sqlite.repository import SqliteRepository
from doc_agent.adapters.sqlite.search_index import SqliteSearchIndex
from doc_agent.application.documents import DocumentLifecycle
from doc_agent.domain.errors import DocumentInactiveError, NotFoundError
from doc_agent.domain.models import (
    Block,
    BlockKind,
    Container,
    ExtractedDocument,
    ExtractedVisual,
    XlsxLocator,
)

LOCATOR = XlsxLocator(sheet="MOG", row=2, cell_range="A2:B2")


def _document(name: str, text: str, image: bytes | None = None) -> ExtractedDocument:
    return ExtractedDocument(
        logical_name=name,
        media_type="application/xlsx",
        containers=[
            Container(stable_key="sheet", kind="worksheet", title="MOG", ordinal=1, source=LOCATOR)
        ],
        blocks=[
            Block(
                stable_key="row-1",
                kind=BlockKind.TABLE_ROW,
                ordinal=1,
                text=text,
                source=LOCATOR,
            )
        ],
        visuals=(
            []
            if image is None
            else [
                ExtractedVisual(
                    stable_key="image-1", media_type="image/png", source=LOCATOR, data=image
                )
            ]
        ),
    )


class _Fixture:
    def __init__(self, tmp_path: Path) -> None:
        self.db = SqliteDatabase(tmp_path / "knowledge.sqlite")
        self.store = FileVisualStore(tmp_path / "visuals")
        self.repo = SqliteRepository(self.db, self.store)
        self.index = SqliteSearchIndex(self.db)
        self.lifecycle = DocumentLifecycle(self.repo, self.index)
        self.project = self.repo.create_project("Demo")

    def ingest(self, name: str, text: str, image: bytes | None = None) -> str:
        document = _document(name, text, image)
        stored = self.repo.save_version(self.project.id, document, f"sha-{name}", changes=[])
        self.index.replace_document(
            self.project.id, stored.document_id, stored.version_id, list(document.blocks)
        )
        return stored.document_id


def test_pausing_withholds_a_document_but_keeps_it(tmp_path: Path) -> None:
    fixture = _Fixture(tmp_path)
    document_id = fixture.ingest("fitgap.xlsx", "Checkout PayPay")

    assert [r.document_id for r in fixture.index.search(fixture.project.id, "PayPay")] == [
        document_id
    ]

    fixture.lifecycle.set_active(document_id, active=False)

    assert fixture.index.search(fixture.project.id, "PayPay") == []
    # Still listed, still has its history: paused is not deleted.
    assert [d.id for d in fixture.repo.list_documents(fixture.project.id)] == [document_id]
    assert fixture.repo.get_document(document_id).active is False
    assert len(fixture.repo.history(document_id)) == 1

    fixture.lifecycle.set_active(document_id, active=True)
    assert [r.document_id for r in fixture.index.search(fixture.project.id, "PayPay")] == [
        document_id
    ]


def test_a_paused_document_reports_itself_instead_of_returning_nothing(tmp_path: Path) -> None:
    fixture = _Fixture(tmp_path)
    document_id = fixture.ingest("fitgap.xlsx", "Checkout PayPay", image=b"png-one")
    fixture.lifecycle.set_active(document_id, active=False)

    # Empty results would be indistinguishable from a document that holds nothing.
    with pytest.raises(DocumentInactiveError, match=re.escape("fitgap.xlsx")):
        fixture.repo.get_table_rows(document_id)
    with pytest.raises(DocumentInactiveError, match=re.escape("fitgap.xlsx")):
        fixture.repo.list_visuals(document_id)


def test_pausing_one_document_leaves_the_others_searchable(tmp_path: Path) -> None:
    fixture = _Fixture(tmp_path)
    paused = fixture.ingest("a.xlsx", "Checkout PayPay")
    kept = fixture.ingest("b.xlsx", "Refund PayPay")

    fixture.lifecycle.set_active(paused, active=False)

    assert [r.document_id for r in fixture.index.search(fixture.project.id, "PayPay")] == [kept]


def test_deleting_removes_the_document_from_the_library_and_the_index(tmp_path: Path) -> None:
    fixture = _Fixture(tmp_path)
    document_id = fixture.ingest("fitgap.xlsx", "Checkout PayPay")

    deleted = fixture.lifecycle.delete(document_id)

    assert deleted.logical_name == "fitgap.xlsx"
    assert fixture.repo.list_documents(fixture.project.id) == []
    assert fixture.index.search(fixture.project.id, "PayPay") == []
    with pytest.raises(NotFoundError):
        fixture.repo.get_document(document_id)

    # Searches already exclude it once the document row is gone, so the index has to be
    # checked directly or rows for a deleted document could sit there unnoticed.
    with fixture.db.read() as conn:
        for table in ("fts_blocks", "blocks", "document_versions", "changes"):
            remaining = conn.execute(
                f"SELECT COUNT(*) AS n FROM {table} WHERE document_id=?", (document_id,)
            ).fetchone()
            assert remaining["n"] == 0, f"{table} still holds rows for the deleted document"


def test_deleting_keeps_a_visual_another_document_still_shows(tmp_path: Path) -> None:
    """Visual content is addressed by hash and stored once, so it is shared."""

    fixture = _Fixture(tmp_path)
    shared = b"shared-png-bytes"
    doomed = fixture.ingest("a.xlsx", "Checkout PayPay", image=shared)
    kept = fixture.ingest("b.xlsx", "Refund PayPay", image=shared)
    stored_path = Path(str(fixture.repo.list_visuals(kept)[0]["stored_path"]))
    assert stored_path.exists()

    fixture.lifecycle.delete(doomed)

    assert stored_path.exists(), "an image another document still references was deleted"
    assert fixture.repo.list_visuals(kept)[0]["stored_path"] == str(stored_path)


def test_deleting_removes_a_visual_nothing_else_references(tmp_path: Path) -> None:
    fixture = _Fixture(tmp_path)
    document_id = fixture.ingest("a.xlsx", "Checkout PayPay", image=b"only-here")
    stored_path = Path(str(fixture.repo.list_visuals(document_id)[0]["stored_path"]))
    assert stored_path.exists()

    fixture.lifecycle.delete(document_id)

    assert not stored_path.exists(), "an orphaned image was left behind"
