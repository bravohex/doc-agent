# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportMissingParameterType=false, reportCallIssue=false, reportArgumentType=false, reportUnusedFunction=false
# Dynamic third-party UI/MCP APIs expose incomplete static types; strict checking remains enabled for domain, application, ports, and typed adapters.
"""One process serving the UI to a person and MCP to agents.

An stdio MCP server is spawned per client and exits with it, so it cannot be shared by
a long-running session the way the UI is. Mounting the MCP streamable-HTTP app onto the
UI's own FastAPI instance gives both audiences a single process on a single port,
rather than one command per audience.
"""

from __future__ import annotations

from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any

from doc_agent.bootstrap import build_container
from doc_agent.interfaces.mcp_server import create_mcp
from doc_agent.interfaces.ui.app import create_ui


def normalize_mcp_path(mcp_path: str) -> str:
    """Accept ``mcp``, ``/mcp`` or ``/mcp/`` and return one canonical mount path."""

    stripped = mcp_path.strip().strip("/")
    if not stripped:
        raise ValueError("mcp_path must name a path, so the UI at / is not shadowed")
    return f"/{stripped}"


def _web() -> Any:
    try:
        from nicegui import app as web_app
    except ImportError as exc:
        raise RuntimeError(
            "NiceGUI is required for `doc-agent serve`; install project dependencies."
        ) from exc
    return web_app


def compose_server(
    *, home: Path, mcp_path: str = "/mcp", max_context_tokens: int = 2_000
) -> tuple[Any, str]:
    """Register both interfaces on the UI's web app, starting no server.

    Composition is separated from ``ui.run`` so the mount and the MCP lifespan — the
    parts that fail silently at runtime — are reachable from a test.
    """

    mount_path = normalize_mcp_path(mcp_path)
    web_app = _web()
    create_ui(build_container(home, max_context_tokens=max_context_tokens), home=home)

    mcp = create_mcp(home, max_context_tokens=max_context_tokens)
    # The app is mounted under mount_path, so its own route must sit at the mount root;
    # otherwise the endpoint would answer at <mount_path><mount_path>.
    mcp.settings.streamable_http_path = "/"
    web_app.mount(mount_path, mcp.streamable_http_app())

    # A mounted ASGI app never receives the parent's lifespan events, so the session
    # manager has to be opened here explicitly or every MCP request fails at runtime.
    lifespan = AsyncExitStack()

    async def _start_mcp() -> None:
        await lifespan.enter_async_context(mcp.session_manager.run())

    async def _stop_mcp() -> None:
        await lifespan.aclose()

    web_app.on_startup(_start_mcp)
    web_app.on_shutdown(_stop_mcp)
    return web_app, mount_path


def run_server(
    *,
    home: Path,
    host: str = "127.0.0.1",
    port: int = 8080,
    mcp_path: str = "/mcp",
    max_context_tokens: int = 2_000,
) -> None:
    """Serve the UI at ``/`` and the MCP endpoint at ``mcp_path`` on one port."""

    compose_server(home=home, mcp_path=mcp_path, max_context_tokens=max_context_tokens)

    from nicegui import ui

    ui.run(host=host, port=port, title="Doc Agent", reload=False, show=False)
