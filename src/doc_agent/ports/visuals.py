"""Visual storage and analysis ports."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class VisualWriteResult(Protocol):
    sha256: str
    path: Path


class VisualStore(Protocol):
    def put(self, data: bytes, *, media_type: str) -> VisualWriteResult: ...


class VisualAnalyzer(Protocol):
    def summarize(self, data: bytes, *, media_type: str, nearby_text: str = "") -> str | None: ...
