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
    XlsxLocator,
)


def test_current_table_rows_and_visual_flags_are_manageable(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "knowledge.sqlite")
    repo = SqliteRepository(db)
    project = repo.create_project("Demo")
    locator = XlsxLocator(sheet="Data", row=2, cell_range="A2:B2")
    document = ExtractedDocument(
        logical_name="data.xlsx",
        media_type="application/xlsx",
        containers=[
            Container(stable_key="sheet", kind="worksheet", title="Data", ordinal=1, source=locator)
        ],
        blocks=[
            Block(
                stable_key="row-1",
                kind=BlockKind.TABLE_ROW,
                ordinal=2,
                text="1\tAlpha",
                source=locator,
                payload={"cells": [{"display": "1"}, {"display": "Alpha"}]},
            )
        ],
        visuals=[
            ExtractedVisual(
                stable_key="image-1",
                media_type="image/png",
                source=locator,
                data=b"png-bytes",
            )
        ],
    )
    stored = repo.save_version(project.id, document, "sha", changes=[])
    rows = repo.get_table_rows(stored.document_id)
    assert rows[0]["text"] == "1\tAlpha"
    visual = repo.list_visuals(stored.document_id)[0]
    repo.update_visual(visual["id"], decorative=True, retrieval_enabled=False, summary="logo")
    updated = repo.list_visuals(stored.document_id)[0]
    assert updated["decorative"] == 1
    assert updated["retrieval_enabled"] == 0
    assert updated["summary"] == "logo"
