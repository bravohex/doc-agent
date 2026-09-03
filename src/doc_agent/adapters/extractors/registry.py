"""Select the first extractor that explicitly supports a source path."""

from __future__ import annotations

from pathlib import Path

from doc_agent.domain.errors import UnsupportedFormatError
from doc_agent.ports.extractors import DocumentExtractor


class ExtractorRegistry:
    """Small open/closed registry: adding a new extractor does not change ingest logic."""

    def __init__(self, extractors: list[DocumentExtractor]) -> None:
        self._extractors = list(extractors)

    def for_file(self, source: Path) -> DocumentExtractor:
        for extractor in self._extractors:
            if extractor.supports(source):
                return extractor
        raise UnsupportedFormatError(f"Unsupported document format: {source.suffix or '<none>'}")
