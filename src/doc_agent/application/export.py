"""Portable knowledge package use case."""

from __future__ import annotations

from pathlib import Path

from doc_agent.ports.export import ProjectExporter


class ExportProject:
    """Delegate portable materialization to an injected exporter adapter."""

    def __init__(self, exporter: ProjectExporter) -> None:
        self.exporter = exporter

    def execute(self, project_id: str, destination: Path) -> Path:
        return self.exporter.export(project_id, destination)
