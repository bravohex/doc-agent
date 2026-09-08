# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportMissingTypeArgument=false, reportUntypedFunctionDecorator=false, reportCallIssue=false, reportArgumentType=false, reportUnusedFunction=false, reportReturnType=false
# Dynamic third-party Office/UI APIs expose incomplete static types; strict checking remains enabled for domain, application, ports, and typed adapters.
"""NiceGUI local application; NiceGUI is imported only when the UI is launched.

The page is wiring: every value it shows is shaped by ``presenter``, and every call
into the application goes through one guard so an expected failure becomes a notice
rather than a stack trace in the terminal.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, TypeVar

from doc_agent.bootstrap import AppContainer, build_container
from doc_agent.domain.errors import DocAgentError
from doc_agent.interfaces.ui import presenter

T = TypeVar("T")

ACCEPTED = ".xlsx,.xlsm,.docx,.pptx,.pdf"
CARD = "w-full p-4 gap-2"
MUTED = "text-sm opacity-60"


@dataclass(slots=True)
class _Selection:
    """Per-client selection; a page function runs once per connected browser."""

    project: str | None = None
    document: str | None = None
    tab: str = "Search"


def _nicegui() -> Any:
    try:
        from nicegui import ui
    except ImportError as exc:
        raise RuntimeError(
            "NiceGUI is required for `doc-agent ui`; install project dependencies."
        ) from exc
    return ui


def create_ui(app: AppContainer, *, home: Path) -> None:
    """Register the pages against an already-composed application."""

    ui = _nicegui()

    def guard(action: Callable[[], T]) -> T | None:
        """Expected failures belong on screen, not in the server log."""

        try:
            return action()
        except DocAgentError as exc:
            ui.notify(str(exc), type="negative", position="top")
            return None

    @ui.page("/")
    def index() -> None:
        selection = _Selection()
        dark = ui.dark_mode()

        # --- chrome ----------------------------------------------------------------
        with ui.header().classes("items-center justify-between px-4 py-2"):
            with ui.row().classes("items-center gap-3 no-wrap"):
                ui.icon("account_tree").classes("text-2xl")
                with ui.column().classes("gap-0"):
                    ui.label("Doc Agent").classes("text-base font-semibold leading-tight")
                    ui.label("Local-first document knowledge").classes(
                        "text-xs opacity-70 leading-tight"
                    )
            with ui.row().classes("items-center gap-3 no-wrap"):
                with ui.row().classes("items-center gap-1 opacity-80 no-wrap"):
                    ui.icon("folder_open").props("size=xs")
                    ui.label(str(home)).classes("text-xs")
                ui.button(icon="dark_mode", on_click=dark.toggle).props(
                    "flat round dense color=white"
                ).tooltip("Toggle dark mode")

        # --- projects --------------------------------------------------------------
        def choose_project(project_id: str) -> None:
            selection.project = project_id
            selection.document = None
            projects.refresh()
            results.refresh()
            library.refresh()
            breadcrumb.refresh()

        def create_project() -> None:
            name = (new_project.value or "").strip()
            if not name:
                ui.notify("Enter a project name", type="warning", position="top")
                return
            project = guard(lambda: app.projects.create(name))
            if project is None:
                return
            new_project.value = ""
            ui.notify(f"Created {project.name}", type="positive", position="top")
            choose_project(project.id)

        @ui.refreshable
        def projects() -> None:
            known = guard(app.projects.list) or []
            if not known:
                ui.label("No projects yet. Create one to get started.").classes(MUTED)
                return
            with ui.list().props("separator").classes("w-full"):
                for project in known:
                    documents = guard(lambda p=project: app.repository.list_documents(p.id)) or []
                    active = project.id == selection.project
                    item = ui.item(on_click=lambda p=project: choose_project(p.id)).mark(
                        f"project-{project.id}"
                    )
                    with item.props("clickable" + (" active" if active else "")), ui.item_section():
                        ui.item_label(project.name).classes("font-medium" if active else "")
                        # The slug is what a person types elsewhere, so it belongs beside
                        # the name rather than only in the CLI.
                        ui.item_label(
                            f"{project.slug} · {_count(len(documents), 'document')}"
                            if project.slug
                            else _count(len(documents), "document")
                        ).props("caption")

        with ui.left_drawer(value=True).props("width=300 bordered").classes("p-4 gap-4"):
            ui.label("Projects").classes("text-xs font-semibold uppercase opacity-60")
            with ui.row().classes("w-full items-center gap-2 no-wrap"):
                new_project = (
                    ui.input(placeholder="New project")
                    .props("dense outlined")
                    .classes("grow")
                    .mark("new-project")
                )
                ui.button(icon="add", on_click=create_project).props("dense unelevated").tooltip(
                    "Create project"
                )
            new_project.on("keydown.enter", create_project)
            projects()

        # --- search ----------------------------------------------------------------
        def run_search() -> None:
            results.refresh()

        @ui.refreshable
        def results() -> None:
            if selection.project is None:
                _placeholder(ui, "search", "Select a project to search it.")
                return
            text = (query.value or "").strip()
            if not text:
                _placeholder(ui, "search", "Type a phrase to search this project.")
                return
            found = guard(lambda: app.search.execute(selection.project or "", text))
            if found is None:
                return
            ui.label(presenter.search_summary(found)).classes(MUTED)
            if not found:
                _placeholder(ui, "search_off", f"Nothing in this project matches “{text}”.")
                return
            for view in presenter.result_views(found):
                _result_card(ui, view)

        @ui.refreshable
        def breadcrumb() -> None:
            project = None
            document = None
            if selection.project:
                project = guard(lambda: app.projects.get(selection.project or ""))
            if selection.document:
                document = guard(lambda: app.repository.get_document(selection.document or ""))
            crumbs = presenter.breadcrumb(project, document, tab=selection.tab)
            with ui.row().classes("w-full items-center gap-1 no-wrap text-sm"):
                for index, crumb in enumerate(crumbs):
                    if index:
                        ui.icon("chevron_right").props("size=xs").classes("opacity-40")
                    classes = "opacity-60" if crumb.muted else ""
                    if index == len(crumbs) - 1 and not crumb.muted:
                        classes = "font-medium"
                    ui.label(crumb.label).classes(classes)
                    if crumb.detail:
                        ui.badge(crumb.detail).props("outline").classes("opacity-70")

        # --- library ---------------------------------------------------------------
        def open_document(document_id: str) -> None:
            selection.document = None if selection.document == document_id else document_id
            library.refresh()
            breadcrumb.refresh()

        def set_active(document_id: str, *, active: bool) -> None:
            document = guard(lambda: app.documents.set_active(document_id, active=active))
            if document is None:
                return
            state = "reads from" if active else "pauses"
            ui.notify(f"Retrieval now {state} {document.logical_name}", position="top")
            library.refresh()

        # One dialog, reused: building it inside the click handler would attach a new
        # element to the refreshable's slot on every click and never release it.
        pending_delete: dict[str, str] = {}

        def confirm_delete() -> None:
            delete_dialog.close()
            document_id, name = pending_delete.get("id", ""), pending_delete.get("name", "")
            if not document_id or guard(lambda: app.documents.delete(document_id)) is None:
                return
            if selection.document == document_id:
                selection.document = None
            ui.notify(f"Deleted {name}", position="top")
            library.refresh()
            projects.refresh()

        with ui.dialog() as delete_dialog, ui.card().classes("gap-2"):
            delete_question = ui.label().classes("font-medium")
            ui.label(
                "Its versions, history, and search entries go too. This cannot be undone."
            ).classes(MUTED)
            with ui.row().classes("w-full justify-end gap-2"):
                ui.button("Cancel", on_click=delete_dialog.close).props("flat")
                ui.button("Delete", on_click=confirm_delete).props("color=negative")

        def delete_document(document_id: str, name: str) -> None:
            """Confirm first: deleting takes the versions and history with it."""

            pending_delete.update(id=document_id, name=name)
            delete_question.set_text(f"Delete {name}?")
            delete_dialog.open()

        @ui.refreshable
        def library() -> None:
            if selection.project is None:
                _placeholder(ui, "library_books", "Select a project to see its documents.")
                return
            documents = guard(lambda: app.repository.list_documents(selection.project or ""))
            if documents is None:
                return
            if not documents:
                _placeholder(ui, "library_books", "This project has no documents yet.")
                return
            for view in presenter.document_views(documents):
                with ui.card().classes(CARD):
                    with ui.row().classes("w-full items-center gap-3 no-wrap"):
                        ui.badge(view.format_label).props("outline")
                        with ui.column().classes("grow gap-0"):
                            name = ui.label(view.name).classes("font-medium")
                            if not view.active:
                                name.classes("opacity-60")
                                ui.label(view.retrieval_label).classes(MUTED)
                        ui.badge(view.version_label).props("color=primary")
                        ui.button(
                            icon="pause" if view.active else "play_arrow",
                            on_click=lambda d=view.document_id, a=view.active: set_active(
                                d, active=not a
                            ),
                        ).props("flat round dense").tooltip(
                            "Pause retrieval" if view.active else "Resume retrieval"
                        )
                        ui.button(
                            icon="delete_outline",
                            on_click=lambda d=view.document_id, n=view.name: delete_document(d, n),
                        ).props("flat round dense color=negative").tooltip("Delete document")
                        ui.button(
                            icon="expand_more"
                            if selection.document != view.document_id
                            else "expand_less",
                            on_click=lambda d=view.document_id: open_document(d),
                        ).props("flat round dense").tooltip("History and visuals")
                    if selection.document == view.document_id:
                        _document_detail(ui, app, guard, view.document_id)

        # --- ingest ----------------------------------------------------------------
        async def upload(event: Any) -> None:
            if selection.project is None:
                ui.notify("Select a project first", type="warning", position="top")
                return
            # Never trust the browser-provided name as a path: reducing it to a basename
            # keeps an uploaded "../name.xlsx" inside the managed upload directory.
            filename = Path(event.file.name).name
            if not filename:
                ui.notify("Uploaded file has no usable name", type="negative", position="top")
                return
            upload_dir = home / "uploads"
            upload_dir.mkdir(parents=True, exist_ok=True)
            target = upload_dir / filename
            target.write_bytes(await event.file.read())
            result = guard(lambda: app.ingest.execute(selection.project or "", target))
            if result is None:
                return
            report.append(
                (
                    filename,
                    presenter.ingest_summary(
                        result.status, result.version_number, len(result.diff.changed)
                    ),
                    presenter.warning_lines(result.warnings),
                )
            )
            ui.notify(f"{filename}: {result.status}", type="positive", position="top")
            outcomes.refresh()
            library.refresh()
            results.refresh()

        report: list[tuple[str, str, list[str]]] = []

        @ui.refreshable
        def outcomes() -> None:
            if not report:
                _placeholder(ui, "history", "Ingested documents appear here.")
                return
            for filename, summary, warnings in reversed(report):
                with ui.card().classes(CARD):
                    with ui.row().classes("w-full items-center gap-2 no-wrap"):
                        ui.icon("description")
                        ui.label(filename).classes("font-medium")
                    ui.label(summary).classes(MUTED)
                    for line in warnings:
                        with ui.row().classes("items-start gap-2 no-wrap"):
                            ui.icon("warning").classes("text-amber-600")
                            ui.label(line).classes("text-sm")

        # --- layout ----------------------------------------------------------------
        def choose_tab(name: str) -> None:
            selection.tab = name
            breadcrumb.refresh()

        def _on_tab_change(event: Any) -> None:
            choose_tab(str(event.value))

        with ui.column().classes("w-full gap-2"):
            breadcrumb()
            with ui.tabs(on_change=_on_tab_change).classes("w-full") as tabs:
                search_tab = ui.tab("Search", icon="search")
                library_tab = ui.tab("Library", icon="library_books")
                add_tab = ui.tab("Add documents", icon="upload_file")
        with ui.tab_panels(tabs, value=search_tab).classes("w-full grow"):
            with ui.tab_panel(search_tab), ui.column().classes("w-full gap-3"):
                with ui.row().classes("w-full items-center gap-2 no-wrap"):
                    query = (
                        ui.input(placeholder="Search this project")
                        .props("outlined dense clearable")
                        .classes("grow")
                        .mark("query")
                    )
                    ui.button("Search", icon="search", on_click=run_search).props("unelevated")
                query.on("keydown.enter", run_search)
                with ui.column().classes("w-full gap-2"):
                    results()
            with ui.tab_panel(library_tab), ui.column().classes("w-full gap-2"):
                library()
            with ui.tab_panel(add_tab), ui.column().classes("w-full gap-3"):
                ui.label(f"Accepted formats: {ACCEPTED.replace(',', ', ')}").classes(MUTED)
                ui.upload(on_upload=upload, auto_upload=True, multiple=True).props(
                    f"accept={ACCEPTED}"
                ).classes("w-full")
                outcomes()


def _document_detail(ui: Any, app: AppContainer, guard: Any, document_id: str) -> None:
    """Versions, the changes each one brought, and the visuals to curate."""

    ui.separator()
    versions = guard(lambda: app.history.execute(document_id)) or []
    with ui.row().classes("items-center gap-2 flex-wrap"):
        ui.label("Versions").classes(MUTED)
        for version in versions:
            ui.badge(f"v{version.version_number}").props("outline")

    for version in reversed(versions):
        changes = guard(partial(app.repository.get_changes, document_id, version.version_number))
        views = presenter.change_views(changes or [])
        if not views:
            continue
        with ui.expansion(f"v{version.version_number} · {_count(len(views), 'change')}").classes(
            "w-full"
        ):
            for view in views:
                with ui.row().classes("w-full items-start gap-2 no-wrap"):
                    ui.badge(view.label).props(f"color={view.colour} outline")
                    with ui.column().classes("gap-0 grow"):
                        ui.label(view.locator).classes("text-xs opacity-60")
                        ui.label(view.text).classes("text-sm")

    visuals = guard(lambda: app.repository.list_visuals(document_id)) or []
    if not visuals:
        return
    ui.label(_count(len(visuals), "visual")).classes(MUTED)
    for visual in visuals:
        _visual_row(ui, app, guard, visual)


def _visual_row(ui: Any, app: AppContainer, guard: Any, visual: dict[str, Any]) -> None:
    """Curation is the only way a visual leaves retrieval, so the page must offer it."""

    def save(*, decorative: bool | None = None, retrieval: bool | None = None) -> None:
        guard(
            lambda: app.repository.update_visual(
                str(visual["id"]),
                decorative=bool(visual["decorative"]) if decorative is None else decorative,
                retrieval_enabled=(
                    bool(visual["retrieval_enabled"]) if retrieval is None else retrieval
                ),
                summary=visual["summary"],
            )
        )

    with ui.row().classes("w-full items-center gap-3 no-wrap"):
        ui.icon("image")
        with ui.column().classes("gap-0 grow"):
            ui.label(presenter.describe_source(_loads(visual["source_json"]))).classes("text-sm")
            ui.label(presenter.describe_format(str(visual["media_type"]))).classes(
                "text-xs opacity-60"
            )

        def set_decorative(event: Any) -> None:
            save(decorative=bool(event.value))

        def set_retrievable(event: Any) -> None:
            save(retrieval=bool(event.value))

        ui.switch("Decorative", value=bool(visual["decorative"]), on_change=set_decorative).props(
            "dense"
        )
        ui.switch(
            "Retrievable", value=bool(visual["retrieval_enabled"]), on_change=set_retrievable
        ).props("dense")


def _result_card(ui: Any, view: presenter.ResultView) -> None:
    with ui.card().classes(CARD):
        with ui.row().classes("w-full items-center gap-2 no-wrap"):
            ui.label(view.document).classes("font-medium")
            ui.badge(view.kind).props("outline")
            ui.badge(view.locator).props("color=secondary outline")
            if view.needs_visual:
                ui.badge("needs the picture").props("color=warning outline")
            ui.space()
            ui.label(view.tokens).classes("text-xs opacity-60")
        ui.label(view.snippet).classes("text-sm whitespace-pre-wrap")
        with ui.row().classes("items-center gap-1 no-wrap"):
            ui.label(view.block_id).classes("text-xs opacity-50 font-mono")
            ui.button(
                icon="content_copy", on_click=lambda: ui.clipboard.write(view.block_id)
            ).props("flat round dense size=sm").tooltip("Copy block id")


def _placeholder(ui: Any, icon: str, message: str) -> None:
    with ui.column().classes("w-full items-center gap-2 py-10 opacity-60"):
        ui.icon(icon).classes("text-4xl")
        ui.label(message).classes("text-sm")


def _count(total: int, noun: str) -> str:
    return f"{total} {noun}" if total == 1 else f"{total} {noun}s"


def _loads(value: object) -> dict[str, Any]:
    import json

    try:
        return dict(json.loads(str(value)))
    except TypeError, ValueError:
        return {}


def run_ui(*, home: Path, host: str = "127.0.0.1", port: int = 8080) -> None:
    """Run a compact local UI for projects, ingestion, search, history, and visuals."""

    ui = _nicegui()
    create_ui(build_container(home), home=home)
    ui.run(host=host, port=port, title="Doc Agent", reload=False, show=False)
