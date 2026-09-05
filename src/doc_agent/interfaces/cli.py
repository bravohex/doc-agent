"""Typer CLI using the same application services as UI and MCP."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from doc_agent.bootstrap import build_container
from doc_agent.domain.errors import DocAgentError
from doc_agent.settings import Settings

app = typer.Typer(help="Build and query compact knowledge packages from XLSX, DOCX, PPTX, and PDF.")
project_app = typer.Typer(help="Manage knowledge projects.")
app.add_typer(project_app, name="project")
console = Console()
SUPPORTED_FORMATS = (".xlsx", ".docx", ".pptx", ".pdf")


def _container():
    settings = Settings.from_env()
    return build_container(settings.home, max_context_tokens=settings.max_context_tokens)


@project_app.command("create")
def project_create(name: str, json_output: bool = typer.Option(False, "--json")) -> None:
    project = _container().projects.create(name)
    if json_output:
        typer.echo(project.model_dump_json())
    else:
        console.print(f"Created [bold]{escape(project.name)}[/bold] ({project.id})")


@project_app.command("show")
def project_show(project_id: str, json_output: bool = typer.Option(False, "--json")) -> None:
    project = _container().projects.get(project_id)
    if json_output:
        typer.echo(project.model_dump_json())
    else:
        console.print(f"[bold]{escape(project.name)}[/bold] ({project.id})")


@project_app.command("list")
def project_list(json_output: bool = typer.Option(False, "--json")) -> None:
    projects = _container().projects.list()
    if json_output:
        typer.echo(json.dumps([p.model_dump(mode="json") for p in projects], default=str))
        return
    table = Table("ID", "Name")
    for project in projects:
        table.add_row(project.id, escape(project.name))
    console.print(table)


@app.command("documents")
def documents(project_id: str) -> None:
    table = Table("ID", "Document", "Version")
    for document in _container().repository.list_documents(project_id):
        table.add_row(
            document.id, escape(document.logical_name), str(document.current_version_number)
        )
    console.print(table)


@app.command("ingest")
def ingest(
    project_id: str, source: Path, replace: str | None = typer.Option(None, "--replace")
) -> None:
    result = _container().ingest.execute(project_id, source, replace_document_id=replace)
    console.print(f"{result.status}: document={result.document_id} version={result.version_number}")
    # Partial extraction is recorded rather than hidden, so it has to be visible here too.
    for warning in result.warnings:
        console.print(f"[yellow]{escape(warning.code)}[/yellow]: {escape(warning.message)}")


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
        # Document text is data, not console markup: FTS wraps every match in brackets,
        # which Rich would otherwise read as a style tag and delete from the output.
        console.print(
            f"[bold]{escape(result.logical_name)}[/bold] "
            f"{escape(str(result.source))}: {escape(result.snippet)}"
        )


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
    console.print(f"Exported to {escape(str(output))}")


@app.command("info")
def info() -> None:
    """Show where this shell would read and write, before anything is created."""

    settings = Settings.from_env()
    table = Table("Setting", "Value", title="Doc Agent")
    table.add_row("Knowledge store", escape(str(settings.home)))
    table.add_row("Store exists", "yes" if settings.home.exists() else "no, created on first use")
    table.add_row("Context budget", f"{settings.max_context_tokens} estimated tokens")
    table.add_row("Formats", ", ".join(SUPPORTED_FORMATS))
    if settings.home.exists():
        projects = _container().projects.list()
        table.add_row("Projects", str(len(projects)))
    console.print(table)


@app.command("ui")
def ui_command(host: str = "127.0.0.1", port: int = 8080) -> None:
    from doc_agent.interfaces.ui.app import run_ui

    run_ui(home=Settings.from_env().home, host=host, port=port)


@app.command("mcp")
def mcp_command() -> None:
    from doc_agent.interfaces.mcp_server import run_mcp

    settings = Settings.from_env()
    run_mcp(home=settings.home, max_context_tokens=settings.max_context_tokens)


def main() -> None:
    """Console-script entry point: expected failures stay messages, not tracebacks.

    ``typer.Exit`` is only meaningful inside a running Click command, so the exit code
    is raised as ``SystemExit`` here.
    """

    try:
        app()
    except DocAgentError as exc:
        console.print(f"[red]{escape(str(exc))}[/red]")
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
