"""A slug has to work everywhere a project id does, or it is a decoration.

The bug this guards against is quiet: a slug reaching a ``WHERE project_id=?`` matches
nothing and reads as an empty project rather than as a wrong argument.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from doc_agent.adapters.sqlite.connection import SqliteDatabase
from doc_agent.adapters.sqlite.repository import SqliteRepository
from doc_agent.domain.errors import NotFoundError, VersionConflictError
from doc_agent.domain.models import (
    Block,
    BlockKind,
    Container,
    ExtractedDocument,
    XlsxLocator,
)
from doc_agent.domain.slugs import InvalidSlugError


@pytest.fixture
def repository(tmp_path: Path) -> SqliteRepository:
    return SqliteRepository(SqliteDatabase(tmp_path / "knowledge.sqlite"))


def _document(name: str) -> ExtractedDocument:
    locator = XlsxLocator(sheet="MOG", row=1, cell_range="A1:B1")
    return ExtractedDocument(
        logical_name=name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        containers=[
            Container(stable_key="sheet", kind="worksheet", title="MOG", ordinal=1, source=locator)
        ],
        blocks=[
            Block(
                stable_key="row-1",
                kind=BlockKind.TABLE_ROW,
                ordinal=1,
                text="PayPay",
                source=locator,
            )
        ],
    )


def test_a_project_gets_a_readable_handle(repository: SqliteRepository) -> None:
    project = repository.create_project("OLM Shopify Plus")

    assert project.slug == "olm-shopify-plus"
    assert repository.list_projects()[0].slug == "olm-shopify-plus"


def test_a_japanese_name_gets_a_generated_handle_or_one_given_by_hand(
    repository: SqliteRepository,
) -> None:
    generated = repository.create_project("株式会社オークローン")
    assert generated.slug.startswith("project-")

    chosen = repository.create_project("見積書 2026", slug="mitsumori-2026")
    assert chosen.slug == "mitsumori-2026"


def test_a_repeated_name_gets_a_distinct_handle(repository: SqliteRepository) -> None:
    first = repository.create_project("OLM")
    second = repository.create_project("OLM")

    assert (first.slug, second.slug) == ("olm", "olm-2")


def test_a_slug_resolves_everywhere_an_id_does(repository: SqliteRepository) -> None:
    """The whole point: a person types the slug and every call still works."""

    project = repository.create_project("OLM Shopify Plus")
    repository.save_version(project.slug, _document("fitgap.xlsx"), "sha", changes=[])

    assert repository.get_project("olm-shopify-plus").id == project.id
    assert repository.resolve_project_id("olm-shopify-plus") == project.id
    # These would silently return nothing if the slug were not resolved first.
    assert [d.logical_name for d in repository.list_documents("olm-shopify-plus")] == [
        "fitgap.xlsx"
    ]
    assert repository.find_document("olm-shopify-plus", "fitgap.xlsx") is not None
    assert repository.project_blocks("olm-shopify-plus")


def test_a_slug_is_matched_regardless_of_case(repository: SqliteRepository) -> None:
    project = repository.create_project("OLM Shopify Plus")

    assert repository.get_project("OLM-Shopify-Plus").id == project.id


def test_an_unknown_handle_is_refused_rather_than_read_as_empty(
    repository: SqliteRepository,
) -> None:
    with pytest.raises(NotFoundError, match="Project not found"):
        repository.list_documents("no-such-project")


def test_a_slug_given_by_hand_is_validated_and_kept_unique(
    repository: SqliteRepository,
) -> None:
    repository.create_project("OLM", slug="olm-plus")

    with pytest.raises(InvalidSlugError):
        repository.create_project("Bad", slug="Not A Slug!")
    with pytest.raises(VersionConflictError, match="already used"):
        repository.create_project("Clash", slug="olm-plus")


_OLD_SCHEMA = """
CREATE TABLE projects (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
INSERT INTO projects VALUES('p1','OLM Shopify Plus','2026-01-01T00:00:00+00:00','2026-01-01T00:00:00+00:00');
INSERT INTO projects VALUES('p2','OLM Shopify Plus','2026-01-02T00:00:00+00:00','2026-01-02T00:00:00+00:00');
"""


def test_projects_created_before_slugs_existed_are_given_one(tmp_path: Path) -> None:
    """A default cannot do this: each project needs a different value, from its name."""

    path = tmp_path / "knowledge.sqlite"
    legacy = sqlite3.connect(path)
    legacy.executescript(_OLD_SCHEMA)
    legacy.commit()
    legacy.close()

    repository = SqliteRepository(SqliteDatabase(path))
    slugs = {project.id: project.slug for project in repository.list_projects()}

    # Oldest first, so the same store always resolves a repeated name the same way.
    assert slugs == {"p1": "olm-shopify-plus", "p2": "olm-shopify-plus-2"}
    assert repository.get_project("olm-shopify-plus").id == "p1"
