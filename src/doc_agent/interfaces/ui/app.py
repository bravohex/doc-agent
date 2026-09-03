# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportMissingTypeArgument=false, reportUntypedFunctionDecorator=false, reportCallIssue=false, reportArgumentType=false, reportUnusedFunction=false, reportReturnType=false
# Dynamic third-party Office/UI APIs expose incomplete static types; strict checking remains enabled for domain, application, ports, and typed adapters.
"""NiceGUI local application; NiceGUI is imported only when the UI is launched."""

from __future__ import annotations

from pathlib import Path

from doc_agent.bootstrap import build_container


def run_ui(*, home: Path, host: str = "127.0.0.1", port: int = 8080) -> None:
    """Run a compact local UI for projects, ingestion, search, diffs, and visuals."""

    try:
        from nicegui import events, ui
    except ImportError as exc:
        raise RuntimeError(
            "NiceGUI is required for `doc-agent ui`; install project dependencies."
        ) from exc

    app = build_container(home)

    @ui.page("/")
    def index() -> None:
        ui.label("Doc Agent").classes("text-2xl font-bold")
        ui.label("Local-first Office knowledge retrieval")
        with ui.row().classes("w-full gap-6"):
            with ui.card().classes("w-96"):
                ui.label("Projects").classes("text-lg font-semibold")
                name = ui.input("New project name")
                project_select = ui.select(
                    {project.id: project.name for project in app.projects.list()},
                    label="Project",
                ).classes("w-full")

                def create_project() -> None:
                    if not name.value:
                        ui.notify("Enter a project name", type="warning")
                        return
                    project = app.projects.create(name.value)
                    project_select.options[project.id] = project.name
                    project_select.update()
                    project_select.value = project.id
                    ui.notify(f"Created {project.name}")

                ui.button("Create", on_click=create_project)
            with ui.card().classes("grow"):
                ui.label("Knowledge Search").classes("text-lg font-semibold")
                query = ui.input("Search text").classes("w-full")
                results = ui.column().classes("w-full")

                def do_search() -> None:
                    results.clear()
                    if not project_select.value or not query.value:
                        return
                    found = app.search.execute(str(project_select.value), query.value)
                    with results:
                        ui.label(
                            f"{len(found)} result(s) · {sum(r.estimated_tokens for r in found)} estimated tokens"
                        )
                        for item in found:
                            with ui.card().classes("w-full"):
                                ui.label(f"{item.logical_name} · {item.kind}").classes(
                                    "font-semibold"
                                )
                                ui.label(item.snippet)
                                ui.label(str(item.source)).classes("text-xs text-gray-500")

                ui.button("Search", on_click=do_search)

        ui.separator()
        ui.label("Ingest document").classes("text-lg font-semibold")
        ingest_status = ui.label("")

        async def upload(event: events.UploadEventArguments) -> None:
            if not project_select.value:
                ui.notify("Select a project first", type="warning")
                return
            upload_dir = home / "uploads"
            upload_dir.mkdir(parents=True, exist_ok=True)
            # NiceGUI exposes the current upload API through event.file. Never trust the
            # browser-provided filename as a path: reducing it to basename prevents an
            # uploaded "../name.xlsx" from escaping the managed upload directory.
            filename = Path(event.file.name).name
            if not filename:
                ui.notify("Uploaded file has no usable name", type="negative")
                return
            target = upload_dir / filename
            target.write_bytes(await event.file.read())
            result = app.ingest.execute(str(project_select.value), target)
            ingest_status.text = f"{result.status} · version {result.version_number} · {len(result.diff.changed)} change(s)"

        ui.upload(on_upload=upload, auto_upload=True).props("accept=.xlsx,.docx,.pptx")

        ui.separator()
        ui.label("Documents / Versions / Visuals").classes("text-lg font-semibold")

        def refresh_documents() -> None:
            if not project_select.value:
                return
            for document in app.repository.list_documents(str(project_select.value)):
                with ui.expansion(f"{document.logical_name} · v{document.current_version_number}"):
                    ui.label(f"Document ID: {document.id}")
                    history = app.history.execute(document.id)
                    ui.label("Versions: " + ", ".join(f"v{v.version_number}" for v in history))
                    visuals = app.repository.list_visuals(document.id)
                    ui.label(f"Visuals: {len(visuals)}")

        ui.button("Refresh document inventory", on_click=refresh_documents)

    ui.run(host=host, port=port, title="Doc Agent", reload=False)
