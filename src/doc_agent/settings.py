"""Local-first runtime settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

STORE_DIRECTORY = ".working"
PROJECT_MARKERS = (".git", "pyproject.toml")
USER_HOME_STORE = "~/.doc-agent"


@dataclass(frozen=True, slots=True)
class Settings:
    home: Path
    max_context_tokens: int = 2_000

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            home=cls.resolve_home(),
            max_context_tokens=cls._positive_int(
                os.environ.get("DOC_AGENT_MAX_CONTEXT_TOKENS"), default=2_000
            ),
        )

    @classmethod
    def resolve_home(cls, start: Path | None = None) -> Path:
        """Keep the knowledge store beside the work it describes.

        A knowledge package belongs to one body of documents, so the default store is
        ``.working`` in the enclosing project rather than a single shared directory in
        the user's home. Work outside any project still needs somewhere to go, and an
        explicit ``DOC_AGENT_HOME`` always wins.
        """

        configured = os.environ.get("DOC_AGENT_HOME")
        if configured:
            return Path(configured).expanduser()
        root = cls.project_root(start or Path.cwd())
        return root / STORE_DIRECTORY if root else Path(USER_HOME_STORE).expanduser()

    @staticmethod
    def project_root(start: Path) -> Path | None:
        """Return the nearest directory that looks like a project root."""

        start = start.resolve()
        for candidate in (start, *start.parents):
            if any((candidate / marker).exists() for marker in PROJECT_MARKERS):
                return candidate
        return None

    @staticmethod
    def _positive_int(value: str | None, *, default: int) -> int:
        """Fall back to the default rather than failing startup on a bad value."""

        try:
            parsed = int(value) if value else default
        except ValueError:
            return default
        return parsed if parsed > 0 else default
