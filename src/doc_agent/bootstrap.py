"""Composition root: the only place concrete adapters are wired into application services."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from doc_agent.adapters.export.package import PackageExporter
from doc_agent.adapters.extractors.docx import DocxExtractor
from doc_agent.adapters.extractors.pdf import PdfExtractor
from doc_agent.adapters.extractors.pptx import PptxExtractor
from doc_agent.adapters.extractors.registry import ExtractorRegistry
from doc_agent.adapters.extractors.xlsx import XlsxExtractor
from doc_agent.adapters.filesystem.visual_store import FileVisualStore
from doc_agent.adapters.sqlite.connection import SqliteDatabase
from doc_agent.adapters.sqlite.repository import SqliteRepository
from doc_agent.adapters.sqlite.search_index import SqliteSearchIndex
from doc_agent.adapters.tokens.heuristic import HeuristicTokenEstimator
from doc_agent.application.documents import DocumentLifecycle
from doc_agent.application.export import ExportProject
from doc_agent.application.history import DocumentHistory
from doc_agent.application.ingest import IngestDocument
from doc_agent.application.projects import ProjectService
from doc_agent.application.retrieve import RetrieveContent
from doc_agent.application.search import SearchDocuments


@dataclass(slots=True)
class AppContainer:
    db: SqliteDatabase
    repository: SqliteRepository
    projects: ProjectService
    ingest: IngestDocument
    search: SearchDocuments
    history: DocumentHistory
    retrieve: RetrieveContent
    export: ExportProject
    documents: DocumentLifecycle


def build_container(home: Path, *, max_context_tokens: int = 2_000) -> AppContainer:
    """Construct one application instance using local filesystem and SQLite adapters."""

    home.mkdir(parents=True, exist_ok=True)
    db = SqliteDatabase(home / "knowledge.sqlite")
    visual_store = FileVisualStore(home / "visuals")
    repository = SqliteRepository(db, visual_store)
    search_index = SqliteSearchIndex(db)
    registry = ExtractorRegistry(
        [XlsxExtractor(), DocxExtractor(), PptxExtractor(), PdfExtractor()]
    )
    return AppContainer(
        db=db,
        repository=repository,
        projects=ProjectService(repository),
        ingest=IngestDocument(registry, repository, search_index),
        search=SearchDocuments(search_index, repository),
        history=DocumentHistory(repository),
        retrieve=RetrieveContent(
            repository, HeuristicTokenEstimator(), max_tokens=max_context_tokens
        ),
        export=ExportProject(PackageExporter(db, repository)),
        documents=DocumentLifecycle(repository, search_index),
    )
