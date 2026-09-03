"""Search use case with a format-agnostic index port."""

from __future__ import annotations

from doc_agent.domain.models import SearchResult
from doc_agent.ports.search import SearchIndex


class SearchDocuments:
    def __init__(self, search_index: SearchIndex) -> None:
        self.search_index = search_index

    def execute(
        self, project_id: str, query: str, *, document_id: str | None = None, limit: int = 20
    ) -> list[SearchResult]:
        return self.search_index.search(project_id, query, document_id=document_id, limit=limit)
