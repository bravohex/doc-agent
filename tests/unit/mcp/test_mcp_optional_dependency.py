from __future__ import annotations

import sys
from pathlib import Path

import pytest

from doc_agent.interfaces.mcp_server import create_mcp


def test_create_mcp_has_actionable_error_without_sdk(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "mcp", None)
    with pytest.raises(RuntimeError, match="MCP SDK"):
        create_mcp(tmp_path)
