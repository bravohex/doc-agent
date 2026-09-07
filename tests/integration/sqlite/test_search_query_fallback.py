"""The quoted-phrase retry exists for FTS5 syntax, and must not stand in for anything
else: a failure with another cause has to surface as itself.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

from doc_agent.adapters.sqlite.connection import SqliteDatabase
from doc_agent.adapters.sqlite.repository import SqliteRepository
from doc_agent.adapters.sqlite.search_index import SqliteSearchIndex
from doc_agent.domain.models import Block, BlockKind, Container, ExtractedDocument, XlsxLocator


def _index(tmp_path: Path) -> tuple[SqliteSearchIndex, str]:
    db = SqliteDatabase(tmp_path / "knowledge.sqlite")
    repo = SqliteRepository(db)
    project = repo.create_project("Demo")
    locator = XlsxLocator(sheet="MOG", row=2, cell_range="A2:B2")
    document = ExtractedDocument(
        logical_name="fitgap.xlsx",
        media_type="application/xlsx",
        containers=[
            Container(stable_key="sheet", kind="worksheet", title="MOG", ordinal=1, source=locator)
        ],
        blocks=[
            Block(
                stable_key="row-1",
                kind=BlockKind.TABLE_ROW,
                ordinal=1,
                text="MOG-001 Checkout PayPay",
                source=locator,
            )
        ],
    )
    stored = repo.save_version(project.id, document, "sha", changes=[])
    index = SqliteSearchIndex(db)
    index.replace_document(project.id, stored.document_id, stored.version_id, list(document.blocks))
    return index, project.id


def test_punctuation_heavy_query_falls_back_to_a_phrase(tmp_path: Path) -> None:
    index, project_id = _index(tmp_path)

    # Bare parentheses are FTS5 syntax; without the retry this raises instead of matching.
    results = index.search(project_id, "MOG-001 (Checkout)")

    assert [r.stable_key for r in results] == ["row-1"]


def test_operators_still_work_when_the_query_is_valid(tmp_path: Path) -> None:
    index, project_id = _index(tmp_path)

    assert [r.stable_key for r in index.search(project_id, "PayPay OR absent")] == ["row-1"]
    assert index.search(project_id, "PayPay NOT Checkout") == []


def test_a_failure_that_is_not_about_syntax_is_not_retried_as_a_phrase(tmp_path: Path) -> None:
    """A programming error must not be reported through the syntax path."""

    index, project_id = _index(tmp_path)
    calls: list[object] = []

    class _FailingConnection:
        def execute(self, *args: object) -> object:
            calls.append(args)
            raise sqlite3.ProgrammingError("closed database")

    class _FailingDatabase:
        @contextmanager
        def read(self) -> Iterator[_FailingConnection]:
            yield _FailingConnection()

    index.db = _FailingDatabase()  # type: ignore[assignment]
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        index.search(project_id, "PayPay")

    assert len(calls) == 1, "the query was retried for a failure the retry cannot fix"
