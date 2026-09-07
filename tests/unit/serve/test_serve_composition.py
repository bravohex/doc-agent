"""The combined server's mount and MCP lifespan fail silently at runtime, so they are
asserted here rather than left to a manual check.

NiceGUI's ``app`` is a process-wide singleton, so each test mounts at its own path.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from doc_agent.interfaces.serve import compose_server, normalize_mcp_path


@pytest.mark.parametrize("given", ["/mcp", "mcp", "mcp/", "/mcp/", "  /mcp/  "])
def test_normalize_mcp_path_accepts_any_spelling(given: str) -> None:
    assert normalize_mcp_path(given) == "/mcp"


@pytest.mark.parametrize("given", ["", "/", "   ", "//"])
def test_normalize_mcp_path_refuses_to_shadow_the_ui(given: str) -> None:
    with pytest.raises(ValueError, match="mcp_path"):
        normalize_mcp_path(given)


def test_compose_server_answers_at_the_mount_path_itself(tmp_path: Path) -> None:
    """The advertised URL is <mount_path>, so the mounted app must route at its root.

    A sub-app that keeps its own default ``/mcp`` route would answer at
    ``/mounted-mcp/mcp`` instead, leaving the documented endpoint dead.
    """

    web_app, mount_path = compose_server(home=tmp_path, mcp_path="/mounted-mcp")

    assert mount_path == "/mounted-mcp"
    mounts = [route for route in web_app.routes if getattr(route, "path", None) == mount_path]
    assert mounts, "the MCP app is not reachable at its mount path"
    assert [getattr(route, "path", None) for route in mounts[0].app.routes] == ["/"]


def test_compose_server_registers_the_mcp_session_lifespan(tmp_path: Path) -> None:
    """Without these hooks the endpoint mounts but every request fails."""

    from nicegui import app as web_app

    before = (len(web_app._startup_handlers), len(web_app._shutdown_handlers))
    compose_server(home=tmp_path, mcp_path="/lifespan-mcp")
    after = (len(web_app._startup_handlers), len(web_app._shutdown_handlers))

    assert after[0] == before[0] + 1, "the MCP session manager would never open"
    assert after[1] == before[1] + 1, "the MCP session manager would never close"


def test_compose_server_has_actionable_error_without_nicegui(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(sys.modules, "nicegui", None)
    with pytest.raises(RuntimeError, match="NiceGUI"):
        compose_server(home=tmp_path, mcp_path="/absent-nicegui")
