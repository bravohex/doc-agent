"""Extraction port."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from doc_agent.domain.models import ExtractedDocument


class ExtractorSelector(Protocol):
    """Select an extractor for a source path."""

    def for_file(self, source: Path) -> "DocumentExtractor": ...


class DocumentExtractor(Protocol):
    """Convert one source format into the normalized domain model."""

    name: str
    version: str

    def supports(self, source: Path) -> bool: ...

    def extract(self, source: Path) -> ExtractedDocument: ...
