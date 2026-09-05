"""Normalized domain model shared by every Office document extractor."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from doc_agent.domain.identifiers import unique_stable_keys

type JsonValue = str | int | float | bool | list[JsonValue] | dict[str, JsonValue] | None
type ChangeKind = Literal[
    "added",
    "changed_semantic",
    "changed_presentation",
    "moved",
    "deleted",
    "unchanged",
]


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""

    return datetime.now(UTC)


class XlsxLocator(BaseModel):
    """Trace an extracted record back to a worksheet position."""

    model_config = ConfigDict(frozen=True)
    kind: Literal["xlsx"] = "xlsx"
    sheet: str
    row: int | None = None
    cell: str | None = None
    cell_range: str | None = None


class DocxLocator(BaseModel):
    """Trace an extracted record back to structural DOCX content."""

    model_config = ConfigDict(frozen=True)
    kind: Literal["docx"] = "docx"
    section_path: tuple[str, ...] = ()
    paragraph_index: int | None = None
    table_index: int | None = None
    row_index: int | None = None
    part: str = "document"
    xml_id: str | None = None


class PptxLocator(BaseModel):
    """Trace an extracted record back to a PowerPoint slide and shape."""

    model_config = ConfigDict(frozen=True)
    kind: Literal["pptx"] = "pptx"
    slide_number: int
    shape_id: int | None = None
    shape_name: str | None = None
    row_index: int | None = None


type SourceLocator = XlsxLocator | DocxLocator | PptxLocator


class BlockKind(StrEnum):
    """Semantic block categories available to retrieval."""

    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"
    TABLE = "table"
    TABLE_ROW = "table_row"
    CELL = "cell"
    TEXT_BOX = "text_box"
    NOTE = "note"
    HEADER = "header"
    FOOTER = "footer"
    CHART = "chart"
    VISUAL_REFERENCE = "visual_reference"


class Block(BaseModel):
    """Smallest independently searchable source-backed content unit."""

    stable_key: str
    kind: BlockKind
    ordinal: int
    text: str
    source: SourceLocator
    container_key: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    presentation: dict[str, Any] = Field(default_factory=dict)
    visual_required: bool = False


class Container(BaseModel):
    """Natural structural unit above blocks: sheet, DOCX section, or slide."""

    stable_key: str
    kind: str
    title: str
    ordinal: int
    source: SourceLocator
    metadata: dict[str, Any] = Field(default_factory=dict)
    visual_required: bool = False


class ExtractedVisual(BaseModel):
    """Embedded or derived visual discovered during extraction."""

    stable_key: str
    kind: str = "image"
    media_type: str
    source: SourceLocator
    data: bytes = Field(repr=False)
    width: int | None = None
    height: int | None = None
    alt_text: str | None = None
    summary: str | None = None
    decorative: bool = False
    retrieval_enabled: bool = True


class ExtractionWarning(BaseModel):
    """Explicitly record partial extraction instead of fabricating semantics."""

    code: str
    message: str
    source: SourceLocator | None = None


class ExtractedDocument(BaseModel):
    """Format-agnostic output returned by every extractor."""

    logical_name: str
    media_type: str
    source_path: str | None = None
    containers: list[Container] = []
    blocks: list[Block] = []
    visuals: list[ExtractedVisual] = []
    warnings: list[ExtractionWarning] = []
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _enforce_unique_block_keys(self) -> ExtractedDocument:
        """Guarantee the invariant persistence relies on, for every extractor.

        A stable key identifies one block inside one version. Enforcing it here rather
        than in each extractor means repeated content surfaces as a distinct block
        instead of a raw database integrity error during ingest.
        """

        keys = [block.stable_key for block in self.blocks]
        if len(set(keys)) != len(keys):
            for block, key in zip(self.blocks, unique_stable_keys(keys), strict=True):
                block.stable_key = key
        return self


class Project(BaseModel):
    """Logical collection of documents queried together."""

    id: str
    name: str
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class DocumentSummary(BaseModel):
    """Current logical document metadata."""

    id: str
    project_id: str
    logical_name: str
    media_type: str
    current_version_id: str | None = None
    current_version_number: int = 0
    source_sha256: str | None = None


class StoredVersion(BaseModel):
    """Persisted immutable document version metadata."""

    version_id: str
    document_id: str
    version_number: int
    source_sha256: str
    created_at: datetime
    media_type: str
    logical_name: str


class Change(BaseModel):
    """Difference between two versions of a stable block."""

    kind: ChangeKind
    stable_key: str
    old_text: str | None = None
    new_text: str | None = None
    old_source: dict[str, Any] | None = None
    new_source: dict[str, Any] | None = None


class DiffResult(BaseModel):
    """Complete normalized diff for one document update."""

    changes: list[Change] = []

    @property
    def changed(self) -> list[Change]:
        """Return changes that need persistence or review."""

        return [change for change in self.changes if change.kind != "unchanged"]


class IngestResult(BaseModel):
    """Result of a first ingest, unchanged detection, or update."""

    status: Literal["created", "updated", "unchanged"]
    document_id: str
    version_id: str
    version_number: int
    diff: DiffResult = Field(default_factory=DiffResult)
    warnings: list[ExtractionWarning] = []


class SearchResult(BaseModel):
    """Compact source-backed full-text search result."""

    block_id: str
    stable_key: str
    document_id: str
    version_id: str
    logical_name: str
    kind: str
    text: str
    snippet: str
    source: dict[str, Any]
    score: float = 0.0
    estimated_tokens: int = 0
    visual_required: bool = False


class StoredVisual(BaseModel):
    """Metadata for content-addressed visual storage."""

    sha256: str
    path: str
    media_type: str
