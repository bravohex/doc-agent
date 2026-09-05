# Architecture

## Design goals

Doc Agent optimizes for four properties:

1. **Source fidelity** — never replace source-backed values with derived summaries.
2. **Retrieval efficiency** — agents read matching blocks, not entire Office files.
3. **Traceability** — every searchable block has a source locator.
4. **Replaceability** — Office parsers, storage, search, UI, and agent protocol are adapters around stable application/domain contracts.

## Dependency direction

```text
interfaces/
    cli
    ui
    mcp
      |
      v
application/
      |
      v
ports/ <------ domain/
  ^
  |
adapters/
```

Rules:

- `domain` imports no adapters or interface frameworks.
- `application` imports domain and ports only.
- concrete Office/SQLite/filesystem dependencies live in `adapters`.
- `bootstrap.py` is the composition root and may import both sides.
- interfaces call application services; they do not open workbooks or issue SQL.

The boundary is tested by `tests/architecture/test_dependency_boundaries.py`.

## Core normalized model

### Container

Natural source unit above a block:

- XLSX: worksheet
- DOCX: heading section
- PPTX: slide

### Block

Smallest normally searchable unit:

- heading / paragraph / list item
- table row
- text box / note
- chart summary

Each block stores:

- stable key
- semantic kind
- text
- structured payload
- presentation metadata
- source locator
- visual-inspection flag

### Visual

Images stay out of normal text context. Their binary is content-addressed by SHA-256 and metadata remains tied to the source locator.

## XLSX fidelity model

Row blocks are compact retrieval units. What a cell says lives in the row payload:

```json
{
  "raw_value": null,
  "formula": "=B17/C17",
  "cached_value": 0.125,
  "display": "12.5%"
}
```

Where and how it is drawn lives in the row presentation, one entry per payload cell at the same index:

```json
{
  "coordinate": "D17",
  "number_format": "0.0%",
  "merged_range": null,
  "hidden_column": false
}
```

The split is what keeps the two hashes honest: inserting a row above shifts every coordinate below it, and if those coordinates sat in the payload the rows would all be reported as semantic changes.

Formula, cached result, and display are deliberately separate. A merged range is metadata; its source value is not copied into cells that were blank in the workbook.

## DOCX model

DOCX is structured by heading hierarchy, not by rendered pages. Pagination depends on rendering engine, fonts, and printer metrics, so page number is not a stable primary source locator.

Tables are emitted as row blocks. Paragraphs retain hyperlink metadata as payload and paragraph style as presentation. Header/footer content is searchable but clearly identified by its source part.

## PPTX model

Slide is the container. Text boxes and table rows are indexed, but position is also preserved because PowerPoint meaning is often spatial.

Diagram-heavy slides can be marked `visual_required`. This prevents the retrieval layer from pretending that a flattened sequence of labels fully describes arrows/relationships.

## PDF model

Page is the container. A PDF states where marks sit on a page and nothing about what they mean, so no heading hierarchy is reconstructed: every text block is a paragraph, and its font size is recorded as presentation for a later classifier to use rather than being guessed at now.

Lines are grouped into a paragraph while they sit directly under one another; a vertical gap larger than the line height, or a change of font size, starts a new one. Lines inside a detected table are left to the table pass so the same content is not stored twice.

A page with no extractable text yields an `ExtractionWarning` naming it as a probable scan. Nothing is inferred from it and no OCR is performed.

Identity is the block text alone. Page number, bounding box, and row index live in the source locator for traceability, which lets content that reflows onto a later page be classified as moved instead of as a deletion and an addition.

## Versioning

### File level

SHA-256 is computed before parsing. An identical source skips extraction entirely.

### Block level

Two hashes are maintained conceptually:

- semantic hash: text + structured payload
- presentation hash: position/style/source-position metadata

Stable-key matching classifies changes without forcing presentation-only edits into semantic re-indexing.

### History

Every changed ingest creates an immutable `document_versions` row and version-specific blocks/visuals. `documents.current_version_id` defines current retrieval state.

Each successful ingest also materializes a collection snapshot pointing to the current version of every document in the project.

## SQLite and FTS5

SQLite is the authoritative knowledge store.

FTS5 contains only current semantic blocks. Updating one document deletes and rebuilds that document's FTS rows, not unrelated project documents.

Search results include:

- stable/block IDs
- source locator
- compact snippet
- logical document name
- estimated token cost
- `visual_required`

## Security model

OOXML files are ZIP archives. Before high-level parsing, `SafeOoxmlPackage` checks:

- traversal paths
- entry count
- per-entry uncompressed size
- total uncompressed size

The code never calls `extractall` on untrusted OOXML packages.

SQLite uses parameterized queries. UI content is rendered through NiceGUI components instead of injecting source HTML.

## Extension points

New source format:

```python
class PdfExtractor:
    name = "pdf"
    version = "1.0"

    def supports(self, source: Path) -> bool: ...
    def extract(self, source: Path) -> ExtractedDocument: ...
```

Then register it in `bootstrap.py`; ingestion/versioning/search need no format-specific changes.

Other extension points:

- tokenizer-aware `TokenEstimator`
- vector/hybrid `SearchIndex`
- external or local `VisualAnalyzer`
- cloud repository adapters
- rendered preview adapters
