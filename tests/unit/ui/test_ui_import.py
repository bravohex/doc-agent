from __future__ import annotations

import sys


def test_ui_module_does_not_require_nicegui_at_import_time(monkeypatch) -> None:
    monkeypatch.setitem(sys.modules, "nicegui", None)
    import doc_agent.interfaces.ui.app as module

    assert callable(module.run_ui)
