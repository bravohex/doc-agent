"""Idempotent SQLite schema for local knowledge persistence."""

from __future__ import annotations

import sqlite3

from doc_agent.domain.slugs import derive_slug

SCHEMA = r"""
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    slug TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    logical_name TEXT NOT NULL,
    media_type TEXT NOT NULL,
    current_version_id TEXT,
    current_version_number INTEGER NOT NULL DEFAULT 0,
    source_sha256 TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    UNIQUE(project_id, logical_name)
);
CREATE TABLE IF NOT EXISTS document_versions (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    source_sha256 TEXT NOT NULL,
    logical_name TEXT NOT NULL,
    media_type TEXT NOT NULL,
    created_at TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    UNIQUE(document_id, version_number)
);
CREATE TABLE IF NOT EXISTS containers (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    version_id TEXT NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
    stable_key TEXT NOT NULL,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    source_json TEXT NOT NULL,
    metadata_json TEXT NOT NULL,
    visual_required INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS blocks (
    block_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    version_id TEXT NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
    stable_key TEXT NOT NULL,
    container_key TEXT,
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
);
CREATE INDEX IF NOT EXISTS idx_blocks_document_version ON blocks(document_id, version_id);
CREATE TABLE IF NOT EXISTS visuals (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL,
    version_id TEXT NOT NULL REFERENCES document_versions(id) ON DELETE CASCADE,
    stable_key TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    media_type TEXT NOT NULL,
    source_json TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    width INTEGER,
    height INTEGER,
    alt_text TEXT,
    summary TEXT,
    decorative INTEGER NOT NULL DEFAULT 0,
    retrieval_enabled INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL,
    version_id TEXT NOT NULL,
    version_number INTEGER NOT NULL,
    kind TEXT NOT NULL,
    stable_key TEXT NOT NULL,
    old_text TEXT,
    new_text TEXT,
    old_source_json TEXT,
    new_source_json TEXT
);
CREATE TABLE IF NOT EXISTS snapshots (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS snapshot_documents (
    snapshot_id TEXT NOT NULL REFERENCES snapshots(id) ON DELETE CASCADE,
    document_id TEXT NOT NULL,
    version_id TEXT NOT NULL,
    PRIMARY KEY(snapshot_id, document_id)
);
CREATE VIRTUAL TABLE IF NOT EXISTS fts_blocks USING fts5(
    block_id UNINDEXED,
    project_id UNINDEXED,
    document_id UNINDEXED,
    version_id UNINDEXED,
    logical_name UNINDEXED,
    stable_key,
    kind UNINDEXED,
    text,
    source_json UNINDEXED,
    visual_required UNINDEXED,
    tokenize='unicode61'
);
"""

# ``CREATE TABLE IF NOT EXISTS`` leaves a database created by an earlier version
# without columns added later, so every additive change is replayed here.
# The slug index is created in ``apply_migrations`` rather than here: on a database that
# predates the column, a statement in this schema would run before the column is added.
ADDED_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("blocks", "container_key", "TEXT"),
    # Documents ingested before retrieval could be paused are active, which is what the
    # default gives them.
    ("documents", "active", "INTEGER NOT NULL DEFAULT 1"),
    # Nullable, because a slug for an existing project has to be derived from its name
    # rather than defaulted; see ``backfill_project_slugs``.
    ("projects", "slug", "TEXT"),
)


def apply_migrations(connection: sqlite3.Connection) -> None:
    """Bring an existing local database up to the current schema."""

    for table, column, declaration in ADDED_COLUMNS:
        columns = {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_slug ON projects(slug) "
        "WHERE slug IS NOT NULL"
    )
    backfill_project_slugs(connection)


def backfill_project_slugs(connection: sqlite3.Connection) -> None:
    """Give projects created before slugs existed one derived from their name.

    A default cannot do this: every project needs a different value, and the value has
    to come from the name. Projects are processed oldest first so the same store always
    resolves a repeated name the same way.
    """

    rows = connection.execute(
        "SELECT id,name FROM projects WHERE slug IS NULL OR slug='' ORDER BY created_at,id"
    ).fetchall()
    if not rows:
        return
    taken = {
        str(row[0])
        for row in connection.execute(
            "SELECT slug FROM projects WHERE slug IS NOT NULL AND slug<>''"
        )
    }
    for project_id, name in rows:
        slug = derive_slug(str(name), taken=taken)
        taken.add(slug)
        connection.execute("UPDATE projects SET slug=? WHERE id=?", (slug, project_id))
