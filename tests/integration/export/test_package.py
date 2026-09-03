from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from doc_agent.bootstrap import build_container


def test_export_contains_manifest_database_tsv_and_source_map(tmp_path: Path) -> None:
    home = tmp_path / "home"
    app = build_container(home)
    project = app.projects.create("Demo")
    source = tmp_path / "a.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.append(["ID", "Name"])
    ws.append(["1", "Alpha"])
    wb.save(source)
    app.ingest.execute(project.id, source)
    dest = tmp_path / "out"
    app.export.execute(project.id, dest)
    assert (dest / "MANIFEST.md").is_file()
    assert (dest / "manifest.json").is_file()
    assert (dest / "knowledge.sqlite").is_file()
    assert (dest / "source-map.jsonl").is_file()
    assert list((dest / "tables").glob("*.tsv"))
