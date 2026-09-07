"""Search-index port."""

from __future__ import annotations

from typing import Protocol

from doc_agent.domain.models import Block, SearchResult


class SearchIndex(Protocol):
    """Index only the current semantic view of a document."""

    def replace_document(
        self, project_id: str, document_id: str, version_id: str, blocks: list[Block]
    ) -> None: ...
    def remove_document(self, document_id: str) -> None: ...
    def search(
        self, project_id: str, query: str, *, document_id: str | None = None, limit: int = 20
    ) -> list[SearchResult]: ...
