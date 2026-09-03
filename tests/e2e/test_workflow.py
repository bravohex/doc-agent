from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook

from doc_agent.bootstrap import build_container


def _xlsx(path: Path, classification: str) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "MOG"
    ws.append(["ID", "Function", "Class"])
    ws.append(["MOG-001", "PayPay", classification])
    wb.save(path)


def test_project_ingest_search_update_history_export(tmp_path: Path) -> None:
    container = build_container(tmp_path / "home")
    project = container.projects.create("OLM")
    source = tmp_path / "fitgap.xlsx"
    _xlsx(source, "A")
    first = container.ingest.execute(project.id, source)
    assert first.status == "created"
    assert container.search.execute(project.id, "PayPay")[0].text.endswith("A")
    unchanged = container.ingest.execute(project.id, source, replace_document_id=first.document_id)
    assert unchanged.status == "unchanged"
    _xlsx(source, "C")
    second = container.ingest.execute(project.id, source, replace_document_id=first.document_id)
    assert second.status == "updated"
    assert any(change.kind == "changed_semantic" for change in second.diff.changes)
    assert len(container.history.execute(first.document_id)) == 2
    out = tmp_path / "export"
    container.export.execute(project.id, out)
    assert (out / "MANIFEST.md").exists()
    assert (out / "knowledge.sqlite").exists()
    assert (out / "source-map.jsonl").exists()
