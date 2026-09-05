"""An unknown id is an error, never an empty result that reads like "nothing here"."""

from __future__ import annotations

from pathlib import Path

import pytest

from doc_agent.bootstrap import build_container
from doc_agent.domain.errors import NotFoundError


def test_lookups_by_unknown_id_all_raise(tmp_path: Path) -> None:
    app = build_container(tmp_path / "home")

    with pytest.raises(NotFoundError, match="Document not found"):
        app.history.execute("missing")
    with pytest.raises(NotFoundError, match="Document not found"):
        app.repository.get_changes("missing", 1)
    with pytest.raises(NotFoundError, match="Project not found"):
        app.repository.list_documents("missing")
    with pytest.raises(NotFoundError, match="Project not found"):
        app.search.execute("missing", "anything")


def test_known_ids_still_answer_with_empty_results(tmp_path: Path) -> None:
    app = build_container(tmp_path / "home")
    project = app.projects.create("Empty")

    assert app.repository.list_documents(project.id) == []
    assert app.search.execute(project.id, "anything") == []
