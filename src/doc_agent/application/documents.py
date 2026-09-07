"""Document lifecycle use cases: pause, resume, and delete.

Pausing and deleting answer two different needs. A paused document keeps every version
it has and can be resumed, which suits a source that is merely stale. Deleting is for a
document that should leave no trace, and it is not reversible.
"""

from __future__ import annotations

from doc_agent.domain.models import DocumentSummary
from doc_agent.ports.repositories import DocumentRepository
from doc_agent.ports.search import SearchIndex


class DocumentLifecycle:
    """Change whether a document exists, or whether retrieval may read it."""

    def __init__(self, repository: DocumentRepository, search_index: SearchIndex) -> None:
        self.repository = repository
        self.search_index = search_index

    def set_active(self, document_id: str, *, active: bool) -> DocumentSummary:
        """Pause or resume one document, leaving its versions and history in place."""

        return self.repository.set_document_active(document_id, active=active)

    def delete(self, document_id: str) -> DocumentSummary:
        """Delete one document permanently, and report what was deleted.

        The index is cleared first: a crash between the two steps should leave a
        document that answers nothing, never one that is gone from the library but
        still returned by search.
        """

        document = self.repository.get_document(document_id)
        self.search_index.remove_document(document_id)
        self.repository.delete_document(document_id)
        return document
