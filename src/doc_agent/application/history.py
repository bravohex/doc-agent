"""Version history use case."""

from __future__ import annotations

from doc_agent.domain.models import StoredVersion
from doc_agent.ports.repositories import DocumentRepository


class DocumentHistory:
    def __init__(self, repository: DocumentRepository) -> None:
        self.repository = repository

    def execute(self, document_id: str) -> list[StoredVersion]:
        return self.repository.history(document_id)
