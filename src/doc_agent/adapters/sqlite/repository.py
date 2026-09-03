"""SQLite repository implementing immutable version/history persistence."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from doc_agent.adapters.filesystem.visual_store import FileVisualStore
from doc_agent.adapters.sqlite.connection import SqliteDatabase
from doc_agent.domain.errors import NotFoundError
from doc_agent.domain.hashing import hash_presentation, hash_semantic
from doc_agent.domain.identifiers import deterministic_block_id
from doc_agent.domain.models import (
    Block,
    BlockKind,
    Change,
    DocxLocator,
    DocumentSummary,
    ExtractedDocument,
    PptxLocator,
    Project,
    StoredVersion,
    XlsxLocator,
)


_LOCATORS = {"xlsx": XlsxLocator, "docx": DocxLocator, "pptx": PptxLocator}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


class SqliteRepository:
    """Persist normalized documents and keep historical blocks available by version."""

    def __init__(self, db: SqliteDatabase, visual_store: FileVisualStore | None = None) -> None:
        self.db = db
        self.visual_store = visual_store or FileVisualStore(db.path.parent / "visuals")

    def create_project(self, name: str) -> Project:
        project = Project(id=str(uuid4()), name=name)
        with self.db.transaction() as conn:
            conn.execute(
                "INSERT INTO projects(id,name,created_at,updated_at) VALUES(?,?,?,?)",
                (project.id, project.name, project.created_at.isoformat(), project.updated_at.isoformat()),
            )
        return project

    def list_projects(self) -> list[Project]:
        with self.db.read() as conn:
            rows = conn.execute("SELECT * FROM projects ORDER BY created_at").fetchall()
        return [Project(id=r["id"], name=r["name"], created_at=r["created_at"], updated_at=r["updated_at"]) for r in rows]

    def get_project(self, project_id: str) -> Project:
        with self.db.read() as conn:
            row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if row is None:
            raise NotFoundError(f"Project not found: {project_id}")
        return Project(id=row["id"], name=row["name"], created_at=row["created_at"], updated_at=row["updated_at"])

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
        with self.db.read() as conn:
            rows = conn.execute(
                "SELECT * FROM documents WHERE project_id=? ORDER BY logical_name", (project_id,)
            ).fetchall()
        return [self._document(row) for row in rows]

    def current_blocks(self, document_id: str) -> list[Block]:
        doc = self.get_document(document_id)
        if not doc.current_version_id:
            return []
        with self.db.read() as conn:
            rows = conn.execute(
                "SELECT * FROM blocks WHERE document_id=? AND version_id=? ORDER BY ordinal",
                (document_id, doc.current_version_id),
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
        now = _utc()
        if document_id is None:
            existing = self.find_document(project_id, document.logical_name)
            document_id = existing.id if existing else str(uuid4())
        try:
            existing_doc = self.get_document(document_id)
        except NotFoundError:
            existing_doc = None
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
                        str(uuid4()), document_id, version_id, container.stable_key, container.kind,
                        container.title, container.ordinal, _json(container.source.model_dump(mode="json")),
                        _json(container.metadata), int(container.visual_required),
                    ),
                )
            for block in document.blocks:
                conn.execute(
                    "INSERT INTO blocks(block_id,document_id,version_id,stable_key,kind,ordinal,text,source_json,payload_json,presentation_json,semantic_hash,presentation_hash,visual_required) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        deterministic_block_id(document_id, block.stable_key), document_id, version_id,
                        block.stable_key, block.kind.value, block.ordinal, block.text,
                        _json(block.source.model_dump(mode="json")), _json(block.payload), _json(block.presentation),
                        hash_semantic(block), hash_presentation(block), int(block.visual_required),
                    ),
                )
            for visual in document.visuals:
                stored = self.visual_store.put(visual.data, media_type=visual.media_type)
                conn.execute(
                    "INSERT INTO visuals(id,document_id,version_id,stable_key,sha256,media_type,source_json,stored_path,width,height,alt_text,summary,decorative,retrieval_enabled) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        str(uuid4()), document_id, version_id, visual.stable_key, stored.sha256,
                        visual.media_type, _json(visual.source.model_dump(mode="json")), str(stored.path),
                        visual.width, visual.height, visual.alt_text, visual.summary,
                        int(visual.decorative), int(visual.retrieval_enabled),
                    ),
                )
            for change in changes:
                conn.execute(
                    "INSERT INTO changes(document_id,version_id,version_number,kind,stable_key,old_text,new_text,old_source_json,new_source_json) VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        document_id, version_id, version_number, change.kind, change.stable_key,
                        change.old_text, change.new_text,
                        _json(change.old_source) if change.old_source is not None else None,
                        _json(change.new_source) if change.new_source is not None else None,
                    ),
                )
            conn.execute(
                "UPDATE documents SET logical_name=?,media_type=?,current_version_id=?,current_version_number=?,source_sha256=? WHERE id=?",
                (document.logical_name, document.media_type, version_id, version_number, source_sha256, document_id),
            )
            snapshot_id = str(uuid4())
            conn.execute("INSERT INTO snapshots(id,project_id,created_at) VALUES(?,?,?)", (snapshot_id, project_id, now))
            current_docs = conn.execute("SELECT id,current_version_id FROM documents WHERE project_id=?", (project_id,)).fetchall()
            for current in current_docs:
                current_version = version_id if current["id"] == document_id else current["current_version_id"]
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
            created_at=now,
            media_type=document.media_type,
            logical_name=document.logical_name,
        )

    def history(self, document_id: str) -> list[StoredVersion]:
        with self.db.read() as conn:
            rows = conn.execute(
                "SELECT * FROM document_versions WHERE document_id=? ORDER BY version_number", (document_id,)
            ).fetchall()
        return [
            StoredVersion(
                version_id=row["id"], document_id=row["document_id"], version_number=row["version_number"],
                source_sha256=row["source_sha256"], created_at=row["created_at"], media_type=row["media_type"],
                logical_name=row["logical_name"],
            )
            for row in rows
        ]

    def get_changes(self, document_id: str, version_number: int) -> list[Change]:
        with self.db.read() as conn:
            rows = conn.execute(
                "SELECT * FROM changes WHERE document_id=? AND version_number=? ORDER BY id",
                (document_id, version_number),
            ).fetchall()
        return [
            Change(
                kind=row["kind"], stable_key=row["stable_key"], old_text=row["old_text"], new_text=row["new_text"],
                old_source=json.loads(row["old_source_json"]) if row["old_source_json"] else None,
                new_source=json.loads(row["new_source_json"]) if row["new_source_json"] else None,
            )
            for row in rows
        ]

    def project_blocks(self, project_id: str) -> list[dict]:
        with self.db.read() as conn:
            rows = conn.execute(
                """SELECT b.*, d.logical_name FROM blocks b JOIN documents d ON d.id=b.document_id
                WHERE d.project_id=? AND b.version_id=d.current_version_id ORDER BY d.logical_name,b.ordinal""",
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_block(self, block_id: str) -> dict:
        with self.db.read() as conn:
            row = conn.execute(
                """SELECT b.*,d.logical_name FROM blocks b JOIN documents d ON d.id=b.document_id
                WHERE b.block_id=? AND b.version_id=d.current_version_id""",
                (block_id,),
            ).fetchone()
        if row is None:
            raise NotFoundError(f"Block not found: {block_id}")
        result = dict(row)
        result["source"] = json.loads(result.pop("source_json"))
        result["payload"] = json.loads(result.pop("payload_json"))
        result["presentation"] = json.loads(result.pop("presentation_json"))
        return result

    def get_table_rows(self, document_id: str) -> list[dict]:
        """Return current-version table rows with decoded structured/source metadata."""

        doc = self.get_document(document_id)
        if not doc.current_version_id:
            return []
        with self.db.read() as conn:
            rows = conn.execute(
                "SELECT * FROM blocks WHERE document_id=? AND version_id=? AND kind='table_row' ORDER BY ordinal",
                (document_id, doc.current_version_id),
            ).fetchall()
        result: list[dict] = []
        for row in rows:
            item = dict(row)
            item["source"] = json.loads(item.pop("source_json"))
            item["payload"] = json.loads(item.pop("payload_json"))
            item["presentation"] = json.loads(item.pop("presentation_json"))
            result.append(item)
        return result

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

    def list_visuals(self, document_id: str) -> list[dict]:
        doc = self.get_document(document_id)
        if not doc.current_version_id:
            return []
        with self.db.read() as conn:
            rows = conn.execute(
                "SELECT * FROM visuals WHERE document_id=? AND version_id=? ORDER BY stable_key",
                (document_id, doc.current_version_id),
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _document(row) -> DocumentSummary:
        return DocumentSummary(
            id=row["id"], project_id=row["project_id"], logical_name=row["logical_name"],
            media_type=row["media_type"], current_version_id=row["current_version_id"],
            current_version_number=row["current_version_number"], source_sha256=row["source_sha256"],
        )

    @staticmethod
    def _row_to_block(row) -> Block:
        source_dict = json.loads(row["source_json"])
        locator = _LOCATORS[source_dict["kind"]].model_validate(source_dict)
        return Block(
            stable_key=row["stable_key"], kind=BlockKind(row["kind"]), ordinal=row["ordinal"], text=row["text"],
            source=locator, payload=json.loads(row["payload_json"]), presentation=json.loads(row["presentation_json"]),
            visual_required=bool(row["visual_required"]),
        )
