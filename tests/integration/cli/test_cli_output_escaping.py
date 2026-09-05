"""Document text reaching the console is data, never console markup."""

from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook
from typer.testing import CliRunner

from doc_agent.interfaces.cli import app


def test_search_output_keeps_the_matched_term(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOC_AGENT_HOME", str(tmp_path / "home"))
    source = tmp_path / "book.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["ID", "Note"])
    sheet.append(["1", "[draft] PayPay settlement"])
    workbook.save(source)

    runner = CliRunner()
    created = runner.invoke(app, ["project", "create", "[Q1] Demo", "--json"])
    assert created.exit_code == 0
    import json

    project_id = json.loads(created.stdout)["id"]
    assert runner.invoke(app, ["ingest", project_id, str(source)]).exit_code == 0

    found = runner.invoke(app, ["search", project_id, "PayPay"])

    assert found.exit_code == 0
    # FTS brackets the match; Rich would read that as a style tag and drop it.
    assert "[PayPay]" in found.stdout
    assert "[draft]" in found.stdout

    listed = runner.invoke(app, ["project", "list"])
    assert "[Q1] Demo" in listed.stdout
