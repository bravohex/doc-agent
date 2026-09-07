"""A store created by an earlier version has to keep working.

``CREATE TABLE IF NOT EXISTS`` leaves an existing database without columns added later,
so opening a real pre-existing store is what this checks -- not a freshly built one,
which would have the column from the schema and prove nothing.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from doc_agent.adapters.sqlite.connection import SqliteDatabase
from doc_agent.adapters.sqlite.repository import SqliteRepository

# The documents table exactly as an earlier version created it: no `active` column.
_OLD_SCHEMA = """
CREATE TABLE projects (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE documents (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    logical_name TEXT NOT NULL,
    media_type TEXT NOT NULL,
    current_version_id TEXT,
    current_version_number INTEGER NOT NULL DEFAULT 0,
    source_sha256 TEXT,
    UNIQUE(project_id, logical_name)
);
INSERT INTO projects VALUES('p1','OLM','2026-01-01T00:00:00+00:00','2026-01-01T00:00:00+00:00');
INSERT INTO documents VALUES('d1','p1','RFP.docx','application/docx',NULL,1,'sha');
"""


def test_a_store_from_an_earlier_version_gains_the_active_column(tmp_path: Path) -> None:
    path = tmp_path / "knowledge.sqlite"
    legacy = sqlite3.connect(path)
    legacy.executescript(_OLD_SCHEMA)
    legacy.commit()
    legacy.close()

    repository = SqliteRepository(SqliteDatabase(path))
    documents = repository.list_documents("p1")

    # Documents that predate pausing are active, so nothing silently stops being found.
    assert [(d.logical_name, d.active) for d in documents] == [("RFP.docx", True)]

    paused = repository.set_document_active("d1", active=False)
    assert paused.active is False
