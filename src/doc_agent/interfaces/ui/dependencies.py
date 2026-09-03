"""UI composition helper kept separate so page code never imports storage internals."""

from __future__ import annotations

from pathlib import Path

from doc_agent.bootstrap import AppContainer, build_container


def ui_container(home: Path) -> AppContainer:
    return build_container(home)
