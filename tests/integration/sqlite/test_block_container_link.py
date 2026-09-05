"""Blocks must keep the link to the sheet, section, or slide they came from."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from openpyxl import Workbook

from doc_agent.adapters.sqlite.connection import SqliteDatabase
from doc_agent.bootstrap import build_container


def test_container_key_survives_persistence(tmp_path: Path) -> None:
    source = tmp_path / "book.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "MOG"
    sheet.append(["ID", "Name"])
    sheet.append(["1", "Alpha"])
    workbook.save(source)

    app = build_container(tmp_path / "home")
    project = app.projects.create("Link")
    result = app.ingest.execute(project.id, source)

    blocks = app.repository.current_blocks(result.document_id)
    assert blocks
    container_keys = {block.container_key for block in blocks}
    assert None not in container_keys

    with sqlite3.connect(tmp_path / "home" / "knowledge.sqlite") as connection:
        connection.row_factory = sqlite3.Row
        stored = {
            str(row["stable_key"])
            for row in connection.execute(
                "SELECT stable_key FROM containers WHERE document_id=?", (result.document_id,)
            )
        }
    assert container_keys <= stored


def test_a_database_without_the_column_is_migrated(tmp_path: Path) -> None:
    path = tmp_path / "old.sqlite"
    with sqlite3.connect(path) as connection:
        # The blocks table exactly as an earlier release created it.
        connection.executescript(
            """CREATE TABLE blocks (
                block_id TEXT NOT NULL,
                document_id TEXT NOT NULL,
                version_id TEXT NOT NULL,
                stable_key TEXT NOT NULL,
                kind TEXT NOT NULL,
                ordinal INTEGER NOT NULL,
                text TEXT NOT NULL,
                source_json TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                presentation_json TEXT NOT NULL,
                semantic_hash TEXT NOT NULL,
                presentation_hash TEXT NOT NULL,
                visual_required INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(version_id, stable_key)
            );"""
        )

    SqliteDatabase(path)

    with sqlite3.connect(path) as connection:
        columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(blocks)")}
    assert "container_key" in columns
