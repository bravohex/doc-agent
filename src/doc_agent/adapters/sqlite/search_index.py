"""SQLite FTS5 implementation returning bounded compact search results."""

from __future__ import annotations

import json

from doc_agent.adapters.sqlite.connection import SqliteDatabase
from doc_agent.adapters.tokens.heuristic import HeuristicTokenEstimator
from doc_agent.domain.identifiers import deterministic_block_id
from doc_agent.domain.models import Block, SearchResult


class SqliteSearchIndex:
    """Keep only current-version semantic blocks in FTS5."""

    def __init__(self, db: SqliteDatabase) -> None:
        self.db = db
        self.tokens = HeuristicTokenEstimator()

    def replace_document(
        self, project_id: str, document_id: str, version_id: str, blocks: list[Block]
    ) -> None:
        with self.db.transaction() as conn:
            logical = conn.execute(
                "SELECT logical_name FROM documents WHERE id=?", (document_id,)
            ).fetchone()
            logical_name = logical["logical_name"] if logical else ""
            conn.execute("DELETE FROM fts_blocks WHERE document_id=?", (document_id,))
            for block in blocks:
                if not block.text.strip():
                    continue
                conn.execute(
                    "INSERT INTO fts_blocks(block_id,project_id,document_id,version_id,logical_name,stable_key,kind,text,source_json,visual_required) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        deterministic_block_id(document_id, block.stable_key),
                        project_id,
                        document_id,
                        version_id,
                        logical_name,
                        block.stable_key,
                        block.kind.value,
                        block.text,
                        json.dumps(block.source.model_dump(mode="json"), ensure_ascii=False),
                        int(block.visual_required),
                    ),
                )

    def search(
        self, project_id: str, query: str, *, document_id: str | None = None, limit: int = 20
    ) -> list[SearchResult]:
        query = query.strip()
        if not query:
            return []
        clauses = ["fts_blocks MATCH ?", "project_id=?"]
        params: list[object] = [query, project_id]
        if document_id:
            clauses.append("document_id=?")
            params.append(document_id)
        params.append(max(1, min(limit, 100)))
        sql = f"""SELECT block_id,stable_key,document_id,version_id,logical_name,kind,text,source_json,
            visual_required,bm25(fts_blocks) AS rank,
            snippet(fts_blocks,7,'[',']',' … ',24) AS snip
            FROM fts_blocks WHERE {" AND ".join(clauses)} ORDER BY rank LIMIT ?"""
        with self.db.read() as conn:
            try:
                rows = conn.execute(sql, params).fetchall()
            except Exception:
                # Quoted fallback makes punctuation-heavy user queries safe for FTS syntax.
                params[0] = f'"{query.replace(chr(34), chr(34) * 2)}"'
                rows = conn.execute(sql, params).fetchall()
        return [
            SearchResult(
                block_id=row["block_id"],
                stable_key=row["stable_key"],
                document_id=row["document_id"],
                version_id=row["version_id"],
                logical_name=row["logical_name"],
                kind=row["kind"],
                text=row["text"],
                snippet=row["snip"] or row["text"][:240],
                source=json.loads(row["source_json"]),
                score=float(row["rank"]),
                estimated_tokens=self.tokens.estimate(row["text"]),
                visual_required=bool(row["visual_required"]),
            )
            for row in rows
        ]
