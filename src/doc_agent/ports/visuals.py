"""Visual storage and analysis ports."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class VisualWriteResult(Protocol):
    """Read-only so an immutable dataclass can satisfy it."""

    @property
    def sha256(self) -> str: ...
    @property
    def path(self) -> Path: ...


class VisualStore(Protocol):
    def put(self, data: bytes, *, media_type: str) -> VisualWriteResult: ...


class VisualAnalyzer(Protocol):
    def summarize(self, data: bytes, *, media_type: str, nearby_text: str = "") -> str | None: ...
