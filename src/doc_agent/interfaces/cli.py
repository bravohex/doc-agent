"""Typer CLI using the same application services as UI and MCP."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from doc_agent.bootstrap import build_container
from doc_agent.domain.errors import DocAgentError
from doc_agent.settings import Settings

app = typer.Typer(help="Build and query compact knowledge packages from XLSX, DOCX, and PPTX.")
project_app = typer.Typer(help="Manage knowledge projects.")
app.add_typer(project_app, name="project")
console = Console()


def _container():
    return build_container(Settings.from_env().home)


@project_app.command("create")
def project_create(name: str, json_output: bool = typer.Option(False, "--json")) -> None:
    project = _container().projects.create(name)
    if json_output:
        typer.echo(project.model_dump_json())
    else:
        console.print(f"Created [bold]{project.name}[/bold] ({project.id})")


@project_app.command("show")
def project_show(project_id: str, json_output: bool = typer.Option(False, "--json")) -> None:
    project = _container().projects.get(project_id)
    if json_output:
        typer.echo(project.model_dump_json())
    else:
        console.print(f"[bold]{project.name}[/bold] ({project.id})")


@project_app.command("list")
def project_list(json_output: bool = typer.Option(False, "--json")) -> None:
    projects = _container().projects.list()
    if json_output:
        typer.echo(json.dumps([p.model_dump(mode="json") for p in projects], default=str))
        return
    table = Table("ID", "Name")
    for project in projects:
        table.add_row(project.id, project.name)
    console.print(table)


@app.command("documents")
def documents(project_id: str) -> None:
    table = Table("ID", "Document", "Version")
    for document in _container().repository.list_documents(project_id):
        table.add_row(document.id, document.logical_name, str(document.current_version_number))
    console.print(table)


@app.command("ingest")
def ingest(
    project_id: str, source: Path, replace: str | None = typer.Option(None, "--replace")
) -> None:
    result = _container().ingest.execute(project_id, source, replace_document_id=replace)
    console.print(f"{result.status}: document={result.document_id} version={result.version_number}")


@app.command("search")
def search(
    project_id: str, query: str, limit: int = 20, json_output: bool = typer.Option(False, "--json")
) -> None:
    results = _container().search.execute(project_id, query, limit=limit)
    if json_output:
        typer.echo(
            json.dumps(
                [r.model_dump(mode="json") for r in results], ensure_ascii=False, default=str
            )
        )
        return
    for result in results:
        console.print(f"[bold]{result.logical_name}[/bold] {result.source}: {result.snippet}")


@app.command("get")
def get_block(block_id: str) -> None:
    typer.echo(
        json.dumps(_container().retrieve.block(block_id), ensure_ascii=False, default=str, indent=2)
    )


@app.command("history")
def history(document_id: str) -> None:
    versions = _container().history.execute(document_id)
    typer.echo(json.dumps([v.model_dump(mode="json") for v in versions], default=str, indent=2))


@app.command("diff")
def diff(document_id: str, version: int = typer.Option(..., "--version")) -> None:
    changes = _container().repository.get_changes(document_id, version)
    typer.echo(
        json.dumps([c.model_dump(mode="json") for c in changes], ensure_ascii=False, indent=2)
    )


@app.command("export")
def export(project_id: str, destination: Path) -> None:
    output = _container().export.execute(project_id, destination)
    console.print(f"Exported to {output}")


@app.command("ui")
def ui_command(host: str = "127.0.0.1", port: int = 8080) -> None:
    from doc_agent.interfaces.ui.app import run_ui

    run_ui(home=Settings.from_env().home, host=host, port=port)


@app.command("mcp")
def mcp_command() -> None:
    from doc_agent.interfaces.mcp_server import run_mcp

    run_mcp(home=Settings.from_env().home)


def main() -> None:
    """Console-script entry point: expected failures stay messages, not tracebacks.

    ``typer.Exit`` is only meaningful inside a running Click command, so the exit code
    is raised as ``SystemExit`` here.
    """

    try:
        app()
    except DocAgentError as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
