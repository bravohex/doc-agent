from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from doc_agent.application.ingest import IngestDocument
from doc_agent.domain.errors import VersionConflictError
from doc_agent.domain.models import DocumentSummary


class RejectingRegistry:
    def for_file(self, source: Path) -> object:
        raise AssertionError("cross-project replacement must fail before extraction")


class ForeignDocumentRepository:
    def __init__(self, digest: str) -> None:
        self.digest = digest

    def get_document(self, document_id: str) -> DocumentSummary:
        return DocumentSummary(
            id=document_id,
            project_id="project-a",
            logical_name="same.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            current_version_id="version-1",
            current_version_number=1,
            source_sha256=self.digest,
        )


class UnusedSearchIndex:
    def replace_document(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("cross-project replacement must fail before indexing")


def test_replace_rejects_foreign_project_before_same_hash_shortcut(tmp_path: Path) -> None:
    source = tmp_path / "same.xlsx"
    source.write_bytes(b"same-source")
    digest = hashlib.sha256(b"same-source").hexdigest()
    ingest = IngestDocument(
        RejectingRegistry(),  # type: ignore[arg-type]
        ForeignDocumentRepository(digest),  # type: ignore[arg-type]
        UnusedSearchIndex(),  # type: ignore[arg-type]
    )

    with pytest.raises(VersionConflictError, match="does not belong to project"):
        ingest.execute("project-b", source, replace_document_id="document-a")
