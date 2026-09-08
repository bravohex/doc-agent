"""Search use case with a format-agnostic index port."""

from __future__ import annotations

from doc_agent.domain.models import SearchResult
from doc_agent.ports.repositories import DocumentRepository
from doc_agent.ports.search import SearchIndex


class SearchDocuments:
    def __init__(self, search_index: SearchIndex, repository: DocumentRepository) -> None:
        self.search_index = search_index
        self.repository = repository

    def execute(
        self, project_id: str, query: str, *, document_id: str | None = None, limit: int = 20
    ) -> list[SearchResult]:
        # Without this an unknown project id is indistinguishable from a project that
        # simply has no match, which sends a caller hunting for the wrong problem.
        # Resolving here matters: the index stores real ids, so a slug reaching it would
        # match nothing and read as "no results" instead of as the project it names.
        project = self.repository.get_project(project_id)
        return self.search_index.search(project.id, query, document_id=document_id, limit=limit)
