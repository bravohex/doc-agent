"""Retrieval records cross into agent context as JSON, where a bare 0 reads as a value
rather than as false. SQLite has no boolean type, so the decode has to restore one.
"""

from __future__ import annotations

from pathlib import Path

from doc_agent.adapters.sqlite.connection import SqliteDatabase
from doc_agent.adapters.sqlite.repository import SqliteRepository
from doc_agent.domain.models import (
    Block,
    BlockKind,
    Container,
    ExtractedDocument,
    ExtractedVisual,
    PptxLocator,
)


def _document() -> ExtractedDocument:
    locator = PptxLocator(slide_number=1, shape_id=2, shape_name="Diagram")
    return ExtractedDocument(
        logical_name="deck.pptx",
        media_type="application/pptx",
        containers=[
            Container(stable_key="slide", kind="slide", title="Flow", ordinal=1, source=locator)
        ],
        blocks=[
            Block(
                stable_key="needs-visual",
                kind=BlockKind.TABLE_ROW,
                ordinal=1,
                text="Checkout\tPayPay",
                source=locator,
                visual_required=True,
            ),
            Block(
                stable_key="text-only",
                kind=BlockKind.TABLE_ROW,
                ordinal=2,
                text="Refund\tCredit card",
                source=locator,
                visual_required=False,
            ),
        ],
        visuals=[
            ExtractedVisual(
                stable_key="image-1", media_type="image/png", source=locator, data=b"png-bytes"
            )
        ],
    )


def test_block_records_report_visual_required_as_a_boolean(tmp_path: Path) -> None:
    repo = SqliteRepository(SqliteDatabase(tmp_path / "knowledge.sqlite"))
    project = repo.create_project("Demo")
    stored = repo.save_version(project.id, _document(), "sha", changes=[])

    rows = {row["stable_key"]: row for row in repo.get_table_rows(stored.document_id)}
    assert rows["needs-visual"]["visual_required"] is True
    assert rows["text-only"]["visual_required"] is False

    block = repo.get_block(rows["needs-visual"]["block_id"])
    assert block["visual_required"] is True


def test_visual_records_report_curation_flags_as_booleans(tmp_path: Path) -> None:
    repo = SqliteRepository(SqliteDatabase(tmp_path / "knowledge.sqlite"))
    project = repo.create_project("Demo")
    stored = repo.save_version(project.id, _document(), "sha", changes=[])

    visual = repo.list_visuals(stored.document_id)[0]
    assert visual["decorative"] is False
    assert visual["retrieval_enabled"] is True

    repo.update_visual(visual["id"], decorative=True, retrieval_enabled=False, summary="logo")
    updated = repo.list_visuals(stored.document_id)[0]
    assert updated["decorative"] is True
    assert updated["retrieval_enabled"] is False
