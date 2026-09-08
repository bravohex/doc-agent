"""SQLite repository implementing immutable version/history persistence."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

from doc_agent.adapters.filesystem.visual_store import FileVisualStore
from doc_agent.adapters.sqlite.connection import SqliteDatabase
from doc_agent.domain.errors import (
    DocumentInactiveError,
    NotFoundError,
    VersionConflictError,
)
from doc_agent.domain.hashing import hash_presentation, hash_semantic
from doc_agent.domain.identifiers import deterministic_block_id
from doc_agent.domain.models import (
    Block,
    BlockKind,
    Change,
    ChangeKind,
    DocumentSummary,
    DocxLocator,
    ExtractedDocument,
    PdfLocator,
    PptxLocator,
    Project,
    SourceLocator,
    StoredVersion,
    XlsxLocator,
)
from doc_agent.ports.repositories import Record, decode_cursor
from doc_agent.ports.visuals import VisualStore


def _utc() -> str:
    """Return a persistable UTC timestamp."""

    return datetime.now(UTC).isoformat()


def _parse_datetime(value: object) -> datetime:
    """Convert persisted ISO timestamps back into typed domain datetimes."""

    return datetime.fromisoformat(str(value))


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _decode_locator(value: str) -> SourceLocator:
    """Decode persisted source metadata without leaking SQLite details into the domain."""

    raw = cast(dict[str, Any], json.loads(value))
    kind = raw.get("kind")
    if kind == "xlsx":
        return XlsxLocator.model_validate(raw)
    if kind == "docx":
        return DocxLocator.model_validate(raw)
    if kind == "pptx":
        return PptxLocator.model_validate(raw)
    if kind == "pdf":
        return PdfLocator.model_validate(raw)
    raise ValueError(f"Unsupported persisted locator kind: {kind!r}")


def _block_record(row: sqlite3.Row) -> Record:
    """Decode one persisted block row for retrieval.

    SQLite has no boolean type, so the flag is restored here. Records reach agents as
    JSON, where a bare ``0`` reads as a value rather than as false, and a caller should
    not have to know which fields came from an INTEGER column.
    """

    record: Record = dict(row)
    record["source"] = cast(dict[str, Any], json.loads(str(record.pop("source_json"))))
    record["payload"] = cast(dict[str, Any], json.loads(str(record.pop("payload_json"))))
    record["presentation"] = cast(dict[str, Any], json.loads(str(record.pop("presentation_json"))))
    record["visual_required"] = bool(record["visual_required"])
    return record


def _apply_cursor(clauses: list[str], params: list[object], after: str | None) -> None:
    """Translate a page boundary into a row-value comparison.

    Ordering and filtering use ``(ordinal, stable_key)`` together, which SQLite compares
    as a row value, so a page can never land in the middle of a repeated ordinal.
    """

    boundary = decode_cursor(after)
    if boundary is None:
        return
    clauses.append("(ordinal,stable_key)>(?,?)")
    params.extend(boundary[1:])


def _visual_record(row: sqlite3.Row) -> Record:
    """Decode one persisted visual row, restoring its curation booleans."""

    record: Record = dict(row)
    record["decorative"] = bool(record["decorative"])
    record["retrieval_enabled"] = bool(record["retrieval_enabled"])
    return record


class SqliteRepository:
    """Persist normalized documents and keep historical blocks available by version."""

    def __init__(self, db: SqliteDatabase, visual_store: VisualStore | None = None) -> None:
        self.db = db
        self.visual_store = visual_store or FileVisualStore(db.path.parent / "visuals")

    def create_project(self, name: str) -> Project:
        project = Project(id=str(uuid4()), name=name)
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO projects(id,name,created_at,updated_at) VALUES(?,?,?,?)",
                (
                    project.id,
                    project.name,
                    project.created_at.isoformat(),
                    project.updated_at.isoformat(),
                ),
            )
        return project

    def list_projects(self) -> list[Project]:
        with self.db.read() as conn:
            rows = conn.execute("SELECT * FROM projects ORDER BY created_at").fetchall()
        return [
            Project(
                id=str(row["id"]),
                name=str(row["name"]),
                created_at=_parse_datetime(row["created_at"]),
                updated_at=_parse_datetime(row["updated_at"]),
            )
            for row in rows
        ]

    def get_project(self, project_id: str) -> Project:
        with self.db.read() as conn:
            row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"Project not found: {project_id}")
        return Project(
            id=str(row["id"]),
            name=str(row["name"]),
            created_at=_parse_datetime(row["created_at"]),
            updated_at=_parse_datetime(row["updated_at"]),
        )

    def find_document(self, project_id: str, logical_name: str) -> DocumentSummary | None:
        with self.db.read() as conn:
            row = conn.execute(
                "SELECT * FROM documents WHERE project_id=? AND logical_name=?",
                (project_id, logical_name),
            ).fetchone()
        return self._document(row) if row else None

    def get_document(self, document_id: str) -> DocumentSummary:
        with self.db.read() as conn:
            row = conn.execute("SELECT * FROM documents WHERE id=?", (document_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"Document not found: {document_id}")
        return self._document(row)

    def list_documents(self, project_id: str) -> list[DocumentSummary]:
        self.get_project(project_id)
        with self.db.read() as conn:
            rows = conn.execute(
                "SELECT * FROM documents WHERE project_id=? ORDER BY logical_name", (project_id,)
            ).fetchall()
        return [self._document(row) for row in rows]

    def _read_version(
        self, document_id: str, version_id: str | None, *, after: str | None = None
    ) -> str | None:
        """Decide which version a read sees, and refuse a version that is not this one's.

        A cursor carries the version its first page came from, so continuing a paged read
        stays on that version even if the document was re-ingested in between. Asking for
        one version while continuing a cursor from another is a contradiction, not a
        preference, so it is reported instead of resolved.
        """

        boundary = decode_cursor(after)
        if boundary is not None:
            if version_id is not None and version_id != boundary[0]:
                raise VersionConflictError(
                    f"Cursor continues version {boundary[0]} but version {version_id} "
                    "was requested; drop one of them."
                )
            version_id = boundary[0]
        document = self._active_document(document_id)
        if version_id is None:
            return document.current_version_id
        with self.db.read() as conn:
            row = conn.execute(
                "SELECT id FROM document_versions WHERE id=? AND document_id=?",
                (version_id, document_id),
            ).fetchone()
        if row is None:
            raise NotFoundError(f"Version not found for {document.logical_name}: {version_id}")
        return version_id

    def _active_document(self, document_id: str) -> DocumentSummary:
        """Resolve a document for retrieval, refusing one whose ingestion is paused."""

        document = self.get_document(document_id)
        if not document.active:
            raise DocumentInactiveError(
                f"Document is paused, so its content is withheld: {document.logical_name}"
            )
        return document

    def set_document_active(self, document_id: str, *, active: bool) -> DocumentSummary:
        """Pause or resume a document's contribution to retrieval, keeping its history."""

        self.get_document(document_id)
        with self.db.transaction() as conn:
            conn.execute("UPDATE documents SET active=? WHERE id=?", (int(active), document_id))
        return self.get_document(document_id)

    def delete_document(self, document_id: str) -> DocumentSummary:
        """Remove a document and everything derived from it, and report what went.

        Versions, containers, blocks, and visual rows follow by cascade. The tables
        that hold no foreign key to the document -- the FTS index, the change log, and
        snapshot membership -- are cleared here, or a deleted document would keep
        answering searches.
        """

        document = self.get_document(document_id)
        with self.db.transaction() as conn:
            orphaned = self._unreferenced_visual_paths(conn, document_id)
            conn.execute("DELETE FROM fts_blocks WHERE document_id=?", (document_id,))
            conn.execute("DELETE FROM changes WHERE document_id=?", (document_id,))
            conn.execute("DELETE FROM snapshot_documents WHERE document_id=?", (document_id,))
            conn.execute("DELETE FROM documents WHERE id=?", (document_id,))
        for path in orphaned:
            self.visual_store.discard(path)
        return document

    @staticmethod
    def _unreferenced_visual_paths(conn: sqlite3.Connection, document_id: str) -> list[str]:
        """Return stored paths that only this document's visuals still reference.

        Visual content is addressed by hash and stored once no matter how many
        documents embed it, so deleting every file this document points at would blank
        images that other documents still show.
        """

        rows = conn.execute(
            """SELECT DISTINCT stored_path FROM visuals WHERE document_id=? AND sha256 NOT IN
            (SELECT sha256 FROM visuals WHERE document_id<>?)""",
            (document_id, document_id),
        ).fetchall()
        return [str(row["stored_path"]) for row in rows]

    def current_blocks(self, document_id: str) -> list[Block]:
        document = self.get_document(document_id)
        if not document.current_version_id:
            return []
        with self.db.read() as conn:
            rows = conn.execute(
                "SELECT * FROM blocks WHERE document_id=? AND version_id=? ORDER BY ordinal",
                (document_id, document.current_version_id),
            ).fetchall()
        return [self._row_to_block(row) for row in rows]

    def save_version(
        self,
        project_id: str,
        document: ExtractedDocument,
        source_sha256: str,
        changes: list[Change],
        *,
        document_id: str | None = None,
    ) -> StoredVersion:
        """Persist a complete immutable version in one transaction."""

        now = _utc()
        if document_id is None:
            existing = self.find_document(project_id, document.logical_name)
            document_id = existing.id if existing else str(uuid4())
        try:
            existing_doc = self.get_document(document_id)
        except NotFoundError:
            existing_doc = None
        if existing_doc is not None and existing_doc.project_id != project_id:
            raise VersionConflictError(
                f"Document {document_id} does not belong to project {project_id}"
            )
        # A logical name is unique per project. Renaming a replaced document onto a name
        # another document already holds would otherwise abort the write half-way through
        # with a raw integrity error instead of an answerable conflict.
        if existing_doc is not None and existing_doc.logical_name != document.logical_name:
            clash = self.find_document(project_id, document.logical_name)
            if clash is not None and clash.id != document_id:
                raise VersionConflictError(
                    f"Project {project_id} already has a document named {document.logical_name}"
                )
        version_number = (existing_doc.current_version_number if existing_doc else 0) + 1
        version_id = str(uuid4())
        with self.db.transaction() as conn:
            if existing_doc is None:
                conn.execute(
                    "INSERT INTO documents(id,project_id,logical_name,media_type,current_version_number) VALUES(?,?,?,?,0)",
                    (document_id, project_id, document.logical_name, document.media_type),
                )
            conn.execute(
                "INSERT INTO document_versions(id,document_id,version_number,source_sha256,logical_name,media_type,created_at,metadata_json) VALUES(?,?,?,?,?,?,?,?)",
                (
                    version_id,
                    document_id,
                    version_number,
                    source_sha256,
                    document.logical_name,
                    document.media_type,
                    now,
                    _json(document.metadata),
                ),
            )
            for container in document.containers:
                conn.execute(
                    "INSERT INTO containers(id,document_id,version_id,stable_key,kind,title,ordinal,source_json,metadata_json,visual_required) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        str(uuid4()),
                        document_id,
                        version_id,
                        container.stable_key,
                        container.kind,
                        container.title,
                        container.ordinal,
                        _json(container.source.model_dump(mode="json")),
                        _json(container.metadata),
                        int(container.visual_required),
                    ),
                )
            for block in document.blocks:
                conn.execute(
                    "INSERT INTO blocks(block_id,document_id,version_id,stable_key,container_key,kind,ordinal,text,source_json,payload_json,presentation_json,semantic_hash,presentation_hash,visual_required) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        deterministic_block_id(document_id, block.stable_key),
                        document_id,
                        version_id,
                        block.stable_key,
                        block.container_key,
                        block.kind.value,
                        block.ordinal,
                        block.text,
                        _json(block.source.model_dump(mode="json")),
                        _json(block.payload),
                        _json(block.presentation),
                        hash_semantic(block),
                        hash_presentation(block),
                        int(block.visual_required),
                    ),
                )
            # Curation (decorative, retrieval_enabled, summary) is human judgement about
            # retrieval, not a fact read out of the source, so a new version inherits it
            # instead of silently resetting every annotation the user made.
            curated = self._visual_curation(conn, document_id, existing_doc)
            for visual in document.visuals:
                stored = self.visual_store.put(visual.data, media_type=visual.media_type)
                prior = curated.get(f"key:{visual.stable_key}") or curated.get(
                    f"sha256:{stored.sha256}"
                )
                summary = visual.summary
                decorative = visual.decorative
                retrieval_enabled = visual.retrieval_enabled
                if prior is not None:
                    decorative = bool(prior["decorative"])
                    retrieval_enabled = bool(prior["retrieval_enabled"])
                    if prior["summary"] is not None:
                        summary = str(prior["summary"])
                conn.execute(
                    "INSERT INTO visuals(id,document_id,version_id,stable_key,sha256,media_type,source_json,stored_path,width,height,alt_text,summary,decorative,retrieval_enabled) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        str(uuid4()),
                        document_id,
                        version_id,
                        visual.stable_key,
                        stored.sha256,
                        visual.media_type,
                        _json(visual.source.model_dump(mode="json")),
                        str(stored.path),
                        visual.width,
                        visual.height,
                        visual.alt_text,
                        summary,
                        int(decorative),
                        int(retrieval_enabled),
                    ),
                )
            for change in changes:
                conn.execute(
                    "INSERT INTO changes(document_id,version_id,version_number,kind,stable_key,old_text,new_text,old_source_json,new_source_json) VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        document_id,
                        version_id,
                        version_number,
                        change.kind,
                        change.stable_key,
                        change.old_text,
                        change.new_text,
                        _json(change.old_source) if change.old_source is not None else None,
                        _json(change.new_source) if change.new_source is not None else None,
                    ),
                )
            conn.execute(
                "UPDATE documents SET logical_name=?,media_type=?,current_version_id=?,current_version_number=?,source_sha256=? WHERE id=?",
                (
                    document.logical_name,
                    document.media_type,
                    version_id,
                    version_number,
                    source_sha256,
                    document_id,
                ),
            )
            snapshot_id = str(uuid4())
            conn.execute(
                "INSERT INTO snapshots(id,project_id,created_at) VALUES(?,?,?)",
                (snapshot_id, project_id, now),
            )
            current_docs = conn.execute(
                "SELECT id,current_version_id FROM documents WHERE project_id=?", (project_id,)
            ).fetchall()
            for current in current_docs:
                current_version = (
                    version_id if current["id"] == document_id else current["current_version_id"]
                )
                if current_version:
                    conn.execute(
                        "INSERT INTO snapshot_documents(snapshot_id,document_id,version_id) VALUES(?,?,?)",
                        (snapshot_id, current["id"], current_version),
                    )
            conn.execute("UPDATE projects SET updated_at=? WHERE id=?", (now, project_id))
        return StoredVersion(
            version_id=version_id,
            document_id=document_id,
            version_number=version_number,
            source_sha256=source_sha256,
            created_at=_parse_datetime(now),
            media_type=document.media_type,
            logical_name=document.logical_name,
        )

    @staticmethod
    def _visual_curation(
        conn: sqlite3.Connection, document_id: str, existing_doc: DocumentSummary | None
    ) -> dict[str, Record]:
        """Index the previous version's visual annotations by identity and by content."""

        if existing_doc is None or not existing_doc.current_version_id:
            return {}
        rows = conn.execute(
            "SELECT stable_key,sha256,decorative,retrieval_enabled,summary FROM visuals WHERE document_id=? AND version_id=?",
            (document_id, existing_doc.current_version_id),
        ).fetchall()
        curation: dict[str, Record] = {}
        for row in rows:
            record = cast(Record, dict(row))
            # A visual that moved keeps its curation through the content hash.
            curation.setdefault(f"sha256:{row['sha256']}", record)
            curation[f"key:{row['stable_key']}"] = record
        return curation

    def history(self, document_id: str) -> list[StoredVersion]:
        # An unknown id must not read as "this document has no history".
        self.get_document(document_id)
        with self.db.read() as conn:
            rows = conn.execute(
                "SELECT * FROM document_versions WHERE document_id=? ORDER BY version_number",
                (document_id,),
            ).fetchall()
        return [
            StoredVersion(
                version_id=str(row["id"]),
                document_id=str(row["document_id"]),
                version_number=int(row["version_number"]),
                source_sha256=str(row["source_sha256"]),
                created_at=_parse_datetime(row["created_at"]),
                media_type=str(row["media_type"]),
                logical_name=str(row["logical_name"]),
            )
            for row in rows
        ]

    def get_changes(self, document_id: str, version_number: int) -> list[Change]:
        self.get_document(document_id)
        with self.db.read() as conn:
            rows = conn.execute(
                "SELECT * FROM changes WHERE document_id=? AND version_number=? ORDER BY id",
                (document_id, version_number),
            ).fetchall()
        result: list[Change] = []
        for row in rows:
            old_source = (
                cast(dict[str, Any], json.loads(str(row["old_source_json"])))
                if row["old_source_json"]
                else None
            )
            new_source = (
                cast(dict[str, Any], json.loads(str(row["new_source_json"])))
                if row["new_source_json"]
                else None
            )
            result.append(
                Change(
                    kind=cast(ChangeKind, str(row["kind"])),
                    stable_key=str(row["stable_key"]),
                    old_text=str(row["old_text"]) if row["old_text"] is not None else None,
                    new_text=str(row["new_text"]) if row["new_text"] is not None else None,
                    old_source=old_source,
                    new_source=new_source,
                )
            )
        return result

    def project_blocks(self, project_id: str) -> list[Record]:
        with self.db.read() as conn:
            rows = conn.execute(
                """SELECT b.*, d.logical_name FROM blocks b JOIN documents d ON d.id=b.document_id
                WHERE d.project_id=? AND b.version_id=d.current_version_id ORDER BY d.logical_name,b.ordinal""",
                (project_id,),
            ).fetchall()
        return [cast(Record, dict(row)) for row in rows]

    def get_block(self, block_id: str, *, version_id: str | None = None) -> Record:
        """Return one block. Without ``version_id`` this reads the current version.

        A block id is derived from the document and the stable key, so the same row keeps
        its id across versions; naming a version is how an earlier copy is read.
        """

        version_clause = "b.version_id=?" if version_id else "b.version_id=d.current_version_id"
        params: list[object] = [block_id] if not version_id else [block_id, version_id]
        with self.db.read() as conn:
            row = conn.execute(
                f"""SELECT b.*,d.logical_name,d.active FROM blocks b JOIN documents d ON d.id=b.document_id
                WHERE b.block_id=? AND {version_clause}""",
                params,
            ).fetchone()
        if row is None:
            raise NotFoundError(f"Block not found: {block_id}")
        if not row["active"]:
            raise DocumentInactiveError(
                f"Document is paused, so its blocks are withheld: {row['logical_name']}"
            )
        record = _block_record(row)
        record.pop("active", None)
        return record

    def get_table_rows(
        self,
        document_id: str,
        *,
        version_id: str | None = None,
        after: str | None = None,
        limit: int | None = None,
    ) -> list[Record]:
        """Return table rows with decoded structured/source metadata.

        ``after`` and ``limit`` page through a large table instead of loading every row
        to read a few. Pass the previous page's last :func:`row_cursor`; it keeps the
        read on one version.
        """

        resolved = self._read_version(document_id, version_id, after=after)
        if not resolved:
            return []
        clauses = ["document_id=?", "version_id=?", "kind='table_row'"]
        params: list[object] = [document_id, resolved]
        _apply_cursor(clauses, params, after)
        sql = f"SELECT * FROM blocks WHERE {' AND '.join(clauses)} ORDER BY ordinal,stable_key"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        with self.db.read() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_block_record(row) for row in rows]

    def get_sheet_rows(
        self,
        document_id: str,
        sheet: str,
        *,
        version_id: str | None = None,
        min_row: int = 1,
        max_row: int | None = None,
        after: str | None = None,
        limit: int | None = None,
    ) -> list[Record]:
        """Return one worksheet's row blocks, bounded by row number.

        The sheet and row live inside the stored locator, so they are filtered in SQL
        rather than by loading the document and discarding most of it.
        """

        resolved = self._read_version(document_id, version_id, after=after)
        if not resolved:
            return []
        clauses = [
            "document_id=?",
            "version_id=?",
            "json_extract(source_json,'$.sheet')=?",
            "json_extract(source_json,'$.row')>=?",
        ]
        params: list[object] = [document_id, resolved, sheet, min_row]
        if max_row is not None:
            clauses.append("json_extract(source_json,'$.row')<=?")
            params.append(max_row)
        _apply_cursor(clauses, params, after)
        sql = f"SELECT * FROM blocks WHERE {' AND '.join(clauses)} ORDER BY ordinal,stable_key"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        with self.db.read() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [_block_record(row) for row in rows]

    def get_version_metadata(self, document_id: str, *, version_id: str | None = None) -> Record:
        """Return what extraction recorded about the document as a whole.

        Workbook-wide facts -- how it calculates, what names its formulas use -- belong
        to no single sheet, so they are stored on the version. Like containers, this was
        written at ingest and had no read path.
        """

        resolved = self._read_version(document_id, version_id)
        if not resolved:
            return {}
        with self.db.read() as conn:
            row = conn.execute(
                "SELECT metadata_json FROM document_versions WHERE id=?", (resolved,)
            ).fetchone()
        if row is None:
            return {}
        return cast(dict[str, Any], json.loads(str(row["metadata_json"])))

    def list_containers(self, document_id: str, *, version_id: str | None = None) -> list[Record]:
        """Return the current version's structural units: sheets, sections, or slides.

        Extraction already records each sheet's state, dimension, and tables; without a
        read path that metadata was written and never surfaced.
        """

        resolved = self._read_version(document_id, version_id)
        if not resolved:
            return []
        with self.db.read() as conn:
            rows = conn.execute(
                "SELECT * FROM containers WHERE document_id=? AND version_id=? ORDER BY ordinal",
                (document_id, resolved),
            ).fetchall()
        records: list[Record] = []
        for row in rows:
            record: Record = dict(row)
            record["source"] = cast(dict[str, Any], json.loads(str(record.pop("source_json"))))
            record["metadata"] = cast(dict[str, Any], json.loads(str(record.pop("metadata_json"))))
            record["visual_required"] = bool(record["visual_required"])
            records.append(record)
        return records

    def update_visual(
        self, visual_id: str, *, decorative: bool, retrieval_enabled: bool, summary: str | None
    ) -> None:
        """Update retrieval annotations without mutating the original visual binary."""

        with self.db.transaction() as conn:
            changed = conn.execute(
                "UPDATE visuals SET decorative=?,retrieval_enabled=?,summary=? WHERE id=?",
                (int(decorative), int(retrieval_enabled), summary, visual_id),
            ).rowcount
        if changed == 0:
            raise NotFoundError(f"Visual not found: {visual_id}")

    def list_visuals(self, document_id: str, *, version_id: str | None = None) -> list[Record]:
        resolved = self._read_version(document_id, version_id)
        if not resolved:
            return []
        with self.db.read() as conn:
            rows = conn.execute(
                "SELECT * FROM visuals WHERE document_id=? AND version_id=? ORDER BY stable_key",
                (document_id, resolved),
            ).fetchall()
        return [_visual_record(row) for row in rows]

    @staticmethod
    def _document(row: sqlite3.Row) -> DocumentSummary:
        return DocumentSummary(
            id=str(row["id"]),
            project_id=str(row["project_id"]),
            logical_name=str(row["logical_name"]),
            media_type=str(row["media_type"]),
            current_version_id=(
                str(row["current_version_id"]) if row["current_version_id"] is not None else None
            ),
            current_version_number=int(row["current_version_number"]),
            source_sha256=(str(row["source_sha256"]) if row["source_sha256"] is not None else None),
            active=bool(row["active"]),
        )

    @staticmethod
    def _row_to_block(row: sqlite3.Row) -> Block:
        return Block(
            stable_key=str(row["stable_key"]),
            container_key=(str(row["container_key"]) if row["container_key"] is not None else None),
            kind=BlockKind(str(row["kind"])),
            ordinal=int(row["ordinal"]),
            text=str(row["text"]),
            source=_decode_locator(str(row["source_json"])),
            payload=cast(dict[str, Any], json.loads(str(row["payload_json"]))),
            presentation=cast(dict[str, Any], json.loads(str(row["presentation_json"]))),
            visual_required=bool(row["visual_required"]),
        )
