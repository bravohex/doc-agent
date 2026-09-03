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
        return cls(home=Path(os.environ.get("DOC_AGENT_HOME", "~/.doc-agent")).expanduser())
