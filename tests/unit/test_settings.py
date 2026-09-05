"""The context budget is configuration, so it has to reach the retrieval use case."""

from __future__ import annotations

from pathlib import Path

import pytest

from doc_agent.bootstrap import build_container
from doc_agent.settings import Settings


def test_home_and_budget_are_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOC_AGENT_HOME", "/tmp/doc-agent-test")
    monkeypatch.setenv("DOC_AGENT_MAX_CONTEXT_TOKENS", "512")

    settings = Settings.from_env()

    assert settings.home == Path("/tmp/doc-agent-test")
    assert settings.max_context_tokens == 512


@pytest.mark.parametrize("value", ["not-a-number", "0", "-5", ""])
def test_an_unusable_budget_falls_back_instead_of_failing_startup(
    value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOC_AGENT_MAX_CONTEXT_TOKENS", value)

    assert Settings.from_env().max_context_tokens == 2_000


def test_the_configured_budget_is_the_default_for_context(tmp_path: Path) -> None:
    app = build_container(tmp_path / "home", max_context_tokens=7)
    project = app.projects.create("Budget")

    assert app.retrieve.max_tokens == 7
    assert app.search.execute(project.id, "anything") == []
