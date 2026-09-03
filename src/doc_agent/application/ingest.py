"""Incremental document ingestion use case."""

from __future__ import annotations

import hashlib
from pathlib import Path

from doc_agent.application.diff import VersionDiffer
from doc_agent.ports.extractors import ExtractorSelector
from doc_agent.domain.models import DiffResult, IngestResult
from doc_agent.ports.repositories import DocumentRepository
from doc_agent.ports.search import SearchIndex


class IngestDocument:
    """Hash first, extract only changed sources, persist transactionally, then re-index."""

    def __init__(
        self,
        registry: ExtractorSelector,
        repository: DocumentRepository,
        search_index: SearchIndex,
        differ: VersionDiffer | None = None,
    ) -> None:
        self.registry = registry
        self.repository = repository
        self.search_index = search_index
        self.differ = differ or VersionDiffer()

    def execute(
        self, project_id: str, source: Path, *, replace_document_id: str | None = None
    ) -> IngestResult:
        digest = self._sha256(source)
        existing = (
            self.repository.get_document(replace_document_id)
            if replace_document_id
            else self.repository.find_document(project_id, source.name)
        )
        if existing and existing.source_sha256 == digest and existing.current_version_id:
            return IngestResult(
                status="unchanged", document_id=existing.id, version_id=existing.current_version_id,
                version_number=existing.current_version_number,
            )
        extractor = self.registry.for_file(source)
        extracted = extractor.extract(source)
        old_blocks = self.repository.current_blocks(existing.id) if existing else []
        diff = self.differ.compare(old_blocks, extracted.blocks)
        stored = self.repository.save_version(
            project_id,
            extracted,
            digest,
            diff.changed,
            document_id=existing.id if existing else replace_document_id,
        )
        self.search_index.replace_document(project_id, stored.document_id, stored.version_id, extracted.blocks)
        return IngestResult(
            status="updated" if existing else "created",
            document_id=stored.document_id,
            version_id=stored.version_id,
            version_number=stored.version_number,
            diff=diff,
            warnings=extracted.warnings,
        )

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
