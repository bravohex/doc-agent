# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportMissingTypeArgument=false, reportUntypedFunctionDecorator=false, reportCallIssue=false, reportArgumentType=false, reportUnusedFunction=false, reportReturnType=false
# Dynamic third-party Office/UI APIs expose incomplete static types; strict checking remains enabled for domain, application, ports, and typed adapters.
"""Read-oriented MCP server exposing retrieval-efficient document tools."""

from __future__ import annotations

from pathlib import Path

from doc_agent.bootstrap import build_container


def create_mcp(home: Path, *, max_context_tokens: int = 2_000):
    """Create the MCP server lazily so normal package imports do not require the SDK."""

    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError(
            "MCP SDK is required for `doc-agent mcp`; install project dependencies."
        ) from exc

    app = build_container(home, max_context_tokens=max_context_tokens)
    mcp = FastMCP("doc-agent")

    @mcp.tool()
    def list_projects() -> list[dict]:
        return [p.model_dump(mode="json") for p in app.projects.list()]

    @mcp.tool()
    def list_documents(project_id: str) -> list[dict]:
        return [d.model_dump(mode="json") for d in app.repository.list_documents(project_id)]

    @mcp.tool()
    def search_documents(project_id: str, query: str, limit: int = 10) -> list[dict]:
        return [
            r.model_dump(mode="json") for r in app.search.execute(project_id, query, limit=limit)
        ]

    @mcp.tool()
    def get_block(block_id: str) -> dict:
        return app.retrieve.block(block_id)

    @mcp.tool()
    def get_context(block_ids: list[str], max_tokens: int | None = None) -> list[dict]:
        """Omit max_tokens to use the server's configured context budget."""

        return app.retrieve.context(block_ids, max_tokens=max_tokens)

    @mcp.tool()
    def get_table_rows(document_id: str) -> list[dict]:
        return app.repository.get_table_rows(document_id)

    @mcp.tool()
    def list_visuals(document_id: str) -> list[dict]:
        return app.repository.list_visuals(document_id)

    @mcp.tool()
    def document_history(document_id: str) -> list[dict]:
        return [v.model_dump(mode="json") for v in app.history.execute(document_id)]

    @mcp.tool()
    def diff_document_version(document_id: str, version_number: int) -> list[dict]:
        return [
            c.model_dump(mode="json")
            for c in app.repository.get_changes(document_id, version_number)
        ]

    return mcp


def run_mcp(*, home: Path, max_context_tokens: int = 2_000) -> None:
    create_mcp(home, max_context_tokens=max_context_tokens).run()
