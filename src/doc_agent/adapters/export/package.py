"""Export compact agent navigation artifacts alongside authoritative SQLite data."""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

from doc_agent.adapters.sqlite.connection import SqliteDatabase
from doc_agent.adapters.sqlite.repository import SqliteRepository


class PackageExporter:
    """Materialize a portable project snapshot without changing source semantics."""

    def __init__(self, db: SqliteDatabase, repository: SqliteRepository) -> None:
        self.db = db
        self.repository = repository

    def export(self, project_id: str, destination: Path) -> Path:
        destination.mkdir(parents=True, exist_ok=True)
        (destination / "tables").mkdir(exist_ok=True)
        (destination / "visuals").mkdir(exist_ok=True)
        project = self.repository.get_project(project_id)
        documents = self.repository.list_documents(project_id)
        blocks = self.repository.project_blocks(project_id)
        manifest = {
            "project": project.model_dump(mode="json"),
            "documents": [document.model_dump(mode="json") for document in documents],
            "block_count": len(blocks),
        }
        (destination / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
        )
        lines = [f"# Project: {project.name}", "", "## Documents", ""]
        for document in documents:
            lines.append(
                f"- {document.logical_name}: v{document.current_version_number}, id `{document.id}`"
            )
        lines.extend(["", f"Current searchable blocks: {len(blocks)}", ""])
        (destination / "MANIFEST.md").write_text("\n".join(lines), encoding="utf-8")
        shutil.copy2(self.db.path, destination / "knowledge.sqlite")

        source_map = destination / "source-map.jsonl"
        with source_map.open("w", encoding="utf-8") as handle:
            for row in blocks:
                handle.write(
                    json.dumps(
                        {"block_id": row["block_id"], "stable_key": row["stable_key"], "source": json.loads(row["source_json"])},
                        ensure_ascii=False,
                    )
                    + "\n"
                )

        grouped: dict[str, list[dict]] = {}
        for row in blocks:
            if row["kind"] == "table_row":
                grouped.setdefault(row["logical_name"], []).append(row)
        for logical_name, rows in grouped.items():
            safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in logical_name)
            with (destination / "tables" / f"{safe_name}.tsv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, delimiter="\t")
                writer.writerow(["block_id", "stable_key", "text", "source"])
                for row in rows:
                    writer.writerow([row["block_id"], row["stable_key"], row["text"], row["source_json"]])

        for document in documents:
            for visual in self.repository.list_visuals(document.id):
                source = Path(visual["stored_path"])
                if source.exists():
                    target = destination / "visuals" / source.name
                    if not target.exists():
                        shutil.copy2(source, target)
        return destination
