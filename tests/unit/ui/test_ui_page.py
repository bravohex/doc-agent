"""The page has to actually render; wiring is where the last UI defects lived."""

from __future__ import annotations

from pathlib import Path

from nicegui.testing import User

from doc_agent.bootstrap import build_container
from doc_agent.interfaces.ui.app import create_ui


async def test_an_empty_store_renders_with_guidance(user: User, tmp_path: Path) -> None:
    home = tmp_path / "home"
    create_ui(build_container(home), home=home)

    await user.open("/")

    await user.should_see("Doc Agent")
    await user.should_see("No projects yet. Create one to get started.")
    await user.should_see("Select a project to search it.")


def _workbook(path: Path) -> None:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "MOG"
    sheet.append(["ID", "Function"])
    sheet.append(["MOG-001", "PayPay settlement"])
    workbook.save(path)


async def test_a_project_can_be_created_from_the_page(user: User, tmp_path: Path) -> None:
    home = tmp_path / "home"
    create_ui(build_container(home), home=home)

    await user.open("/")
    user.find(marker="new-project").type("OLM")
    user.find("add").click()

    await user.should_see("OLM")
    await user.should_see("0 documents")


async def test_search_names_the_document_and_the_place_it_came_from(
    user: User, tmp_path: Path
) -> None:
    home = tmp_path / "home"
    app = build_container(home)
    project = app.projects.create("OLM")
    source = tmp_path / "fitgap.xlsx"
    _workbook(source)
    app.ingest.execute(project.id, source)
    create_ui(app, home=home)

    await user.open("/")
    await user.should_see("1 document")
    user.find(marker=f"project-{project.id}").click()
    user.find(marker="query").type("PayPay")
    user.find("Search").click()

    await user.should_see("fitgap.xlsx")
    await user.should_see("Sheet MOG · row 2")
    await user.should_see("table row")


async def test_searching_a_project_with_no_match_says_so(user: User, tmp_path: Path) -> None:
    home = tmp_path / "home"
    app = build_container(home)
    project = app.projects.create("OLM")
    create_ui(app, home=home)

    await user.open("/")
    user.find(marker=f"project-{project.id}").click()
    user.find(marker="query").type("absent")
    user.find("Search").click()

    await user.should_see("No matches")
