from __future__ import annotations

import sys


def test_mcp_module_does_not_require_sdk_at_import_time(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "mcp", None)
    import doc_agent.interfaces.mcp_server as module

    assert callable(module.run_mcp)
