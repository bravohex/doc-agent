from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from doc_agent.interfaces.cli import app


def test_cli_project_create_and_list(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DOC_AGENT_HOME", str(tmp_path / "home"))
    runner = CliRunner()
    created = runner.invoke(app, ["project", "create", "OLM"])
    assert created.exit_code == 0
    listed = runner.invoke(app, ["project", "list"])
    assert listed.exit_code == 0
    assert "OLM" in listed.stdout
