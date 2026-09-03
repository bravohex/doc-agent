from __future__ import annotations

import sys
from pathlib import Path

import pytest

from doc_agent.interfaces.ui.app import run_ui


def test_run_ui_has_actionable_error_without_nicegui(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "nicegui", None)
    with pytest.raises(RuntimeError, match="NiceGUI"):
        run_ui(home=tmp_path)
