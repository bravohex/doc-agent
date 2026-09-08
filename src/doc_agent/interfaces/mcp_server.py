# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportMissingTypeArgument=false, reportUntypedFunctionDecorator=false, reportCallIssue=false, reportArgumentType=false, reportUnusedFunction=false, reportReturnType=false
# Dynamic third-party Office/UI APIs expose incomplete static types; strict checking remains enabled for domain, application, ports, and typed adapters.
"""Read-oriented MCP server exposing retrieval-efficient document tools."""

from __future__ import annotations

from pathlib import Path

from doc_agent.application.retrieve import ContextMode
from doc_agent.application.sheets import DEFAULT_ROW_LIMIT, MAX_ROW_LIMIT
from doc_agent.bootstrap import build_container
from doc_agent.ports.repositories import row_cursor


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
        """Search one project. Raise ``limit`` only when a wider sweep is needed.

        This default is deliberately lower than the CLI's, because every result here is
        spent from an agent's context rather than read by a person on a terminal.
        """

        return [
            r.model_dump(mode="json") for r in app.search.execute(project_id, query, limit=limit)
        ]

    @mcp.tool()
    def get_block(block_id: str, version_id: str | None = None) -> dict:
        """Return one block in full: values, formulas, and formatting. No budget.

        Omit ``version_id`` for the current version. A block keeps its id across
        versions, so naming one reads that earlier copy.
        """

        return app.retrieve.block(block_id, version_id=version_id)

    @mcp.tool()
    def get_context(
        block_ids: list[str],
        max_tokens: int | None = None,
        mode: ContextMode = "text",
        version_id: str | None = None,
    ) -> list[dict]:
        """Return blocks whose whole response fits the budget.

        ``mode`` chooses how much of each block to spend the budget on: ``text`` is the
        content alone, ``cells`` adds values and formulas, ``full`` adds formatting.
        Omit ``max_tokens`` to use the server's configured budget.

        Every record reports the ``mode`` it was actually rendered in, which may be
        cheaper than the one asked for, plus ``truncated`` and -- when identity and
        source alone exceed the budget -- ``budget_exceeded``.
        """

        return app.retrieve.context(
            block_ids, max_tokens=max_tokens, mode=mode, version_id=version_id
        )

    @mcp.tool()
    def get_table_rows(
        document_id: str,
        cursor: str | None = None,
        limit: int | None = None,
        version_id: str | None = None,
    ) -> dict:
        """Return a page of a document's table rows, in document order.

        Pass the returned ``next_cursor`` back as ``cursor`` for the next page; a null
        ``next_cursor`` means this was the last one. The cursor carries the version, so
        a paged read stays on one version even if the document is re-ingested midway.
        Pass ``version_id`` to pin from the first page.
        """

        page_size = DEFAULT_ROW_LIMIT if limit is None else max(1, min(limit, MAX_ROW_LIMIT))
        rows = app.repository.get_table_rows(
            document_id, version_id=version_id, after=cursor, limit=page_size + 1
        )
        has_more = len(rows) > page_size
        page = rows[:page_size]
        document = app.repository.get_document(document_id)
        read_version = (
            str(page[0]["version_id"]) if page else (version_id or document.current_version_id)
        )
        return {
            "rows": page,
            "version_id": read_version,
            "is_current_version": read_version == document.current_version_id,
            "next_cursor": row_cursor(page[-1]) if has_more and page else None,
        }

    @mcp.tool()
    def list_sheets(document_id: str, version_id: str | None = None) -> list[dict]:
        """Describe a workbook's sheets: order, visibility, extent, and defined tables."""

        return app.sheets.sheets(document_id, version_id=version_id)

    @mcp.tool()
    def get_sheet_range(
        document_id: str,
        sheet: str,
        range: str | None = None,
        fields: list[str] | None = None,
        cursor: str | None = None,
        limit: int | None = None,
        version_id: str | None = None,
    ) -> dict:
        """Read cells by address, the way a spreadsheet is normally referenced.

        ``range`` takes A1 notation -- ``B2:D10``, ``B:D``, ``2:10``, or a single
        ``B2`` -- and defaults to the whole sheet. ``fields`` selects what each cell
        carries (default: display, raw_value, formula, cached_value); the coordinate is
        always included. Page with ``cursor``/``limit`` rather than reading a whole
        sheet to reach a few rows.
        """

        return app.sheets.range(
            document_id,
            sheet,
            range,
            fields=fields,
            cursor=cursor,
            limit=limit,
            version_id=version_id,
        )

    @mcp.tool()
    def list_visuals(document_id: str, version_id: str | None = None) -> list[dict]:
        return app.repository.list_visuals(document_id, version_id=version_id)

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
