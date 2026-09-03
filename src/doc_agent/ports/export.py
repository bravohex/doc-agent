"""Portable package export port."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol


class ProjectExporter(Protocol):
    """Export one project to a portable filesystem package."""

    def export(self, project_id: str, destination: Path) -> Path: ...
