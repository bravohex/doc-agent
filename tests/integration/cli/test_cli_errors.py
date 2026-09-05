"""Expected domain failures reach the console script as messages, not tracebacks."""

from __future__ import annotations

from pathlib import Path

import pytest

from doc_agent.interfaces.cli import main


def test_console_script_reports_domain_errors_with_exit_code_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DOC_AGENT_HOME", str(tmp_path / "home"))
    monkeypatch.setattr("sys.argv", ["doc-agent", "project", "show", "missing"])

    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 2
    assert "Project not found" in capsys.readouterr().out
