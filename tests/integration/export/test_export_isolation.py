from __future__ import annotations

import sqlite3
from pathlib import Path

from openpyxl import Workbook

from doc_agent.bootstrap import build_container


def _workbook(path: Path, value: str) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "S"
    sheet.append(["ID", "Value"])
    sheet.append(["R1", value])
    workbook.save(path)


def test_export_package_never_contains_another_projects_data(tmp_path: Path) -> None:
    """The shipped SQLite file is the authoritative export; it must not leak siblings."""

    container = build_container(tmp_path / "home")
    confidential = container.projects.create("CLIENT-SECRET")
    shared = container.projects.create("PUBLIC")

    secret_source = tmp_path / "secret.xlsx"
    _workbook(secret_source, "MERGER-PRICE-9000000")
    public_source = tmp_path / "public.xlsx"
    _workbook(public_source, "harmless")
    container.ingest.execute(confidential.id, secret_source)
    container.ingest.execute(shared.id, public_source)

    destination = tmp_path / "export"
    container.export.execute(shared.id, destination)

    exported = sqlite3.connect(destination / "knowledge.sqlite")
    try:
        assert exported.execute("SELECT id FROM projects").fetchall() == [(shared.id,)]
        assert (
            exported.execute("SELECT text FROM blocks WHERE text LIKE '%MERGER%'").fetchall() == []
        )
        assert (
            exported.execute("SELECT text FROM fts_blocks WHERE text LIKE '%MERGER%'").fetchall()
            == []
        )
        assert exported.execute("SELECT count(*) FROM changes").fetchone()[0] >= 0
        assert exported.execute("SELECT text FROM blocks WHERE text LIKE '%harmless%'").fetchall()
    finally:
        exported.close()
