from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from doc_agent.interfaces.cli import app


def test_cli_project_show(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DOC_AGENT_HOME", str(tmp_path / "home"))
    runner = CliRunner()
    created = runner.invoke(app, ["project", "create", "Demo", "--json"])
    assert created.exit_code == 0
    import json

    project_id = json.loads(created.stdout)["id"]
    shown = runner.invoke(app, ["project", "show", project_id, "--json"])
    assert shown.exit_code == 0
    assert json.loads(shown.stdout)["name"] == "Demo"
