"""Local-first runtime settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    home: Path
    max_context_tokens: int = 2_000

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            home=Path(os.environ.get("DOC_AGENT_HOME", "~/.doc-agent")).expanduser(),
            max_context_tokens=cls._positive_int(
                os.environ.get("DOC_AGENT_MAX_CONTEXT_TOKENS"), default=2_000
            ),
        )

    @staticmethod
    def _positive_int(value: str | None, *, default: int) -> int:
        """Fall back to the default rather than failing startup on a bad value."""

        try:
            parsed = int(value) if value else default
        except ValueError:
            return default
        return parsed if parsed > 0 else default
