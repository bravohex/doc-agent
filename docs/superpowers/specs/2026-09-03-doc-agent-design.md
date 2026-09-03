# Doc Agent — Architecture and Product Design

Date: 2026-09-03
Status: Proposed for implementation
Repository: `bravohex/doc-agent`

## 1. Purpose

Doc Agent converts Office Open XML documents into a compact, traceable knowledge package that software agents can query without loading entire source files into context.

The initial supported formats are:

- `.xlsx`
- `.docx`
- `.pptx`

The system prioritizes two qualities that are often in tension:

1. **Source fidelity** — preserve source values, formulas, document structure, visual assets, and source locations as far as the underlying format allows.
2. **Retrieval efficiency** — let an agent locate and fetch only the small set of relevant blocks, rows, tables, or visuals required for a question.

The application is local-first. A user can ingest and update documents through a browser-based UI, automation can use a CLI, and agents can use an MCP server. All three interfaces use the same application core and SQLite knowledge store.

## 2. Success Criteria

A release is acceptable when it can:

1. Ingest XLSX, DOCX, and PPTX documents into a common normalized model.
2. Preserve source references for every indexed content block.
3. Extract embedded images and register visual metadata without forcing images into normal text retrieval.
4. Build a project manifest and per-document summaries for rapid agent navigation.
5. Search content with SQLite FTS5 and return compact source-backed results.
6. Re-ingest a modified source file and update only added, changed, or deleted semantic blocks.
7. Keep unchanged block identities stable whenever a durable source identifier or structural match exists.
8. Show version diffs in the UI.
9. Expose the same ingest, search, retrieve, history, diff, and visual operations through CLI and MCP.
10. Pass unit, contract, integration, architecture, typing, and lint checks.

## 3. Explicit Non-Goals for the First Release

The first release will not claim perfect round-trip reconstruction of an Office document. It is an extraction and retrieval system, not an Office editor.

The first release also excludes:

- Editing source Office files.
- Cloud multi-user accounts, authentication, or shared tenancy.
- Automatic OCR of all images.
- Mandatory use of an external LLM or vision provider.
- Guaranteed rendering parity with Microsoft Office.
- Full semantic reconstruction of every SmartArt or arbitrary drawing connector graph.
- PDF ingestion. PDF is a future extractor that must fit the same port contract.
- Vector embeddings as a required dependency. FTS5 is the default retrieval engine; vector search is an extension point.

## 4. Product Shape

The application has five primary UI areas:

1. **Projects** — create/open a knowledge project and view its current snapshot.
2. **Documents** — upload or replace XLSX, DOCX, and PPTX files and inspect extraction status.
3. **Version Diff** — review added, changed, deleted, and presentation-only changes.
4. **Knowledge Search** — test retrieval, inspect context, and see an estimated token count.
5. **Visuals** — preview extracted visual assets and include or exclude them from retrieval metadata.

The standard workflow is:

```text
Create project
  -> add source documents
  -> ingest
  -> inspect manifest/search results
  -> replace a changed source document
  -> review diff
  -> accept current snapshot
  -> query through UI, CLI, or MCP
```

## 5. Architecture

The codebase follows a ports-and-adapters layout with dependency direction enforced by tests.

```text
UI / CLI / MCP
       |
       v
Application use cases
       |
       v
Domain model and ports
       ^
       |
Adapters: OOXML extractors, SQLite, filesystem, optional visual analyzers
```

### 5.1 Package Layout

```text
src/doc_agent/
├── domain/
│   ├── models.py
│   ├── identifiers.py
│   ├── hashing.py
│   └── errors.py
├── application/
│   ├── ingest.py
│   ├── update.py
│   ├── search.py
│   ├── retrieve.py
│   ├── diff.py
│   ├── history.py
│   └── projects.py
├── ports/
│   ├── extractors.py
│   ├── repositories.py
│   ├── search.py
│   ├── visuals.py
│   ├── clocks.py
│   └── tokens.py
├── adapters/
│   ├── extractors/
│   │   ├── registry.py
│   │   ├── xlsx.py
│   │   ├── docx.py
│   │   ├── pptx.py
│   │   └── ooxml.py
│   ├── sqlite/
│   │   ├── connection.py
│   │   ├── migrations.py
│   │   ├── repository.py
│   │   └── search_index.py
│   ├── filesystem/
│   │   └── visual_store.py
│   ├── rendering/
│   │   └── libreoffice.py
│   ├── tokens/
│   │   └── heuristic.py
│   └── visuals/
│       └── null_analyzer.py
├── interfaces/
│   ├── cli.py
│   ├── mcp_server.py
│   └── ui/
│       ├── app.py
│       ├── dependencies.py
│       ├── pages/
│       └── components/
├── bootstrap.py
└── settings.py
```

Tests mirror these boundaries:

```text
tests/
├── unit/
├── contract/
├── integration/
├── architecture/
└── fixtures/
```

### 5.2 SOLID Boundaries

- Extractors perform source extraction only.
- The version differ compares normalized documents only.
- Repositories persist data only.
- Search indexes retrieve content only.
- Renderers and visual analyzers are optional adapters.
- UI, CLI, and MCP invoke application use cases; they do not call `openpyxl`, `python-docx`, `python-pptx`, or SQLite directly.
- The domain and application packages do not import framework-specific packages.

Public ports use `typing.Protocol` so implementations remain replaceable without unnecessary inheritance.

## 6. Domain Model

### 6.1 Project

A project groups documents and defines a current collection snapshot.

Core fields:

- `project_id`
- `name`
- `created_at`
- `updated_at`
- `current_snapshot_id`

### 6.2 Document

A document identifies one logical source across versions.

Core fields:

- `document_id`
- `project_id`
- `logical_name`
- `media_type`
- `source_path`
- `current_version_id`

Replacing `estimate.xlsx` with an updated file creates a new document version, not a new document, when the user targets the existing logical document.

### 6.3 Document Version

Core fields:

- `version_id`
- `document_id`
- `version_number`
- `source_sha256`
- `created_at`
- `extractor_name`
- `extractor_version`
- `status`
- extraction statistics and warnings

### 6.4 Container

A container is the natural structural retrieval unit above a block:

- XLSX: worksheet and table/block region
- DOCX: section under a heading hierarchy
- PPTX: slide

Core fields:

- `container_id`
- `document_version_id`
- `kind`
- `logical_key`
- `title`
- `ordinal`
- `source_locator`

### 6.5 Block

A block is the smallest independently indexed semantic unit.

Kinds include:

- `paragraph`
- `heading`
- `list_item`
- `table`
- `table_row`
- `cell`
- `text_box`
- `note`
- `chart`
- `visual_reference`

Core fields:

- `block_id`
- `stable_key`
- `container_id`
- `kind`
- `ordinal`
- `text`
- `structured_payload`
- `semantic_hash`
- `presentation_hash`
- `source_locator`

### 6.6 Visual

Core fields:

- `visual_id`
- `stable_key`
- `document_version_id`
- `container_id`
- `kind`
- `media_type`
- `sha256`
- `width`
- `height`
- `source_locator`
- `stored_path`
- `alt_text`
- `generated_summary`
- `retrieval_enabled`
- `decorative`

### 6.7 Source Locator

Every block and visual contains a typed source locator.

Examples:

```json
{
  "kind": "xlsx",
  "sheet": "MOG",
  "row": 178,
  "range": "A178:J178"
}
```

```json
{
  "kind": "docx",
  "section_path": ["3 Migration", "3.2 Data Migration"],
  "paragraph_index": 187,
  "xml_id": "..."
}
```

```json
{
  "kind": "pptx",
  "slide_number": 7,
  "shape_id": 21,
  "shape_name": "Target architecture"
}
```

The current ordinal is traceability metadata, not necessarily the stable identity.

## 7. Extraction Strategy

### 7.1 Shared OOXML Layer

Office documents are ZIP packages. A shared OOXML helper resolves:

- package parts
- relationships
- embedded media
- content type mappings
- raw XML fallback access

High-level libraries are preferred for normal structures, while raw OOXML is retained as a targeted fallback for data not exposed by those libraries.

### 7.2 XLSX

Primary library: `openpyxl`.

The extractor loads the workbook twice:

- `data_only=False` for formula expressions
- `data_only=True` for cached calculated values

`openpyxl` does not calculate formulas. Cached results are therefore marked as cached source values and may be absent or stale.

The extractor preserves:

- workbook and sheet metadata
- sheet visibility
- non-empty cells
- formula and cached value
- data type
- number format
- a best-effort display value
- hyperlinks and comments
- merged ranges without inventing duplicated raw values
- hidden rows and columns as metadata
- detected contiguous table regions
- defined Excel tables
- embedded images and charts

For normal retrieval, table rows are indexed as compact blocks. Exact cell-level metadata is stored as structured payload and is fetched only when requested.

### 7.3 DOCX

Primary library: `python-docx` plus raw OOXML traversal when ordering or unsupported structures require it.

The extractor preserves:

- heading hierarchy
- paragraphs
- ordered and unordered list items
- tables and rows
- hyperlinks
- captions
- images and relationships
- comments, footnotes, endnotes, headers, and footers where extractable
- style names and limited semantic inline formatting
- tracked-change metadata when present, without silently merging accepted and rejected text

DOCX page numbers are not treated as stable source locations because pagination depends on rendering. Optional LibreOffice rendering may create a PDF/page map, but section path and block identity remain the primary reference.

### 7.4 PPTX

Primary library: `python-pptx` plus raw OOXML for unsupported relationships and chart metadata.

The extractor preserves:

- slide order and titles
- text boxes and placeholder roles
- tables and rows
- speaker notes
- images
- charts and cached series data when available
- shape IDs, names, bounds, and grouping metadata
- connector endpoints on a best-effort basis

Each slide is a container. Text retrieval does not assume that text order alone represents visual relationships. Slides containing diagrams, connectors, or spatially meaningful shapes are marked `visual_required=true`.

Optional LibreOffice rendering can generate slide thumbnails. Absence of LibreOffice must not make ingestion fail.

### 7.5 Visual Handling

Embedded images are copied into a content-addressed filesystem store. Duplicate binaries are stored once.

The default visual analyzer does not call an external API. It records source alt text, dimensions, nearby labels, and format metadata. A future analyzer adapter may add captions or diagram summaries.

Images are not included in normal textual context. Search can return a compact visual reference, and the agent can fetch the image on demand.

Decorative assets such as logos can be disabled from retrieval in the UI.

## 8. Fidelity Rules

1. Raw source values are never overwritten by rendered display values.
2. Formula expression, cached result, number format, and display text are separate fields.
3. A merged-cell value remains attached to the top-left source cell. Readable renderers may repeat it, but stored source data does not.
4. Empty cell, missing cell, and formula returning an empty string remain distinguishable when the source exposes the distinction.
5. Hyperlink labels and targets are stored separately.
6. Presentation metadata is sparse and fetched only when relevant.
7. Extraction warnings are recorded instead of silently fabricating unsupported semantics.
8. A semantic summary is derived data and never replaces source-backed blocks.

## 9. Stable Identity and Versioning

### 9.1 File-Level Detection

Every source is hashed with SHA-256 before extraction.

- Same hash as current version: skip extraction.
- Different hash: extract and compare normalized content.

### 9.2 Stable Keys

Matching priority across versions is:

1. Durable business key found in a configured or clearly identified ID column.
2. Persistent OOXML identifier when available.
3. Structural path plus normalized content fingerprint.
4. Local similarity fallback within the same container.

Row number, paragraph number, or slide number alone must not define stable identity.

### 9.3 Two Hashes

Each block has:

- `semantic_hash` — agent-visible text and structured values
- `presentation_hash` — style, layout, and visual metadata

A presentation-only change updates metadata but does not rebuild the FTS index.

### 9.4 Change States

A version diff classifies records as:

- added
- changed_semantic
- changed_presentation
- moved
- deleted
- unchanged

Deleted blocks remain in version history and are excluded from the current view.

### 9.5 Collection Snapshots

A project snapshot points to one accepted version of every document in the project. Normal searches target the current snapshot. Historical queries can target an older snapshot or version explicitly.

## 10. Storage

SQLite is the authoritative knowledge database. The filesystem stores original source copies when configured, extracted visuals, and optional rendered previews.

### 10.1 Core Tables

- `projects`
- `documents`
- `document_versions`
- `snapshots`
- `snapshot_documents`
- `containers`
- `blocks`
- `block_versions`
- `visuals`
- `visual_versions`
- `ingest_runs`
- `warnings`

### 10.2 FTS5

An FTS5 virtual table indexes current semantic block text and selected structured fields.

Search behavior:

- current snapshot by default
- optional project/document/container filters
- BM25 ranking
- snippets with bounded context
- exact stable-key lookup before full-text fallback
- Unicode tokenizer configuration suitable for Japanese, Vietnamese, and English text, with graceful limitations documented

FTS results always contain source locators and block IDs.

### 10.3 Portable Knowledge Package

The UI can export a project package containing:

```text
project/
├── MANIFEST.md
├── manifest.json
├── knowledge.sqlite
├── tables/
│   └── *.tsv
├── visuals/
└── source-map.jsonl
```

SQLite remains the preferred query layer. TSV is a compact, inspectable representation of extracted tables. Markdown manifests are navigation aids, not the data authority.

## 11. Retrieval API

Application-level operations:

- `create_project`
- `list_projects`
- `ingest_document`
- `replace_document`
- `accept_snapshot`
- `search`
- `get_block`
- `get_context`
- `get_table_rows`
- `get_visual`
- `list_visuals`
- `get_history`
- `diff_versions`
- `export_package`

Search results contain:

- relevance score
- compact snippet
- document and container identity
- source locator
- estimated token count
- flags such as `visual_required`

The context endpoint applies explicit limits by block count and estimated tokens.

## 12. CLI

The CLI uses Typer.

Representative commands:

```bash
doc-agent project create "OLM Shopify Plus"
doc-agent ingest PROJECT_ID ./RFP.docx
doc-agent ingest PROJECT_ID ./estimate.xlsx --replace DOCUMENT_ID
doc-agent search PROJECT_ID "rollback OR ロールバック"
doc-agent diff DOCUMENT_ID --from 3 --to 4
doc-agent history DOCUMENT_ID
doc-agent export PROJECT_ID ./out/
doc-agent ui
doc-agent mcp
```

Commands support machine-readable JSON output where useful.

## 13. UI

The first UI is a local NiceGUI application.

Reasons:

- Python-native integration with the application layer.
- Faster delivery than a separate SPA/Tauri frontend.
- Supports routing, tables, dialogs, uploads, progress, and image previews.
- Can later be wrapped as a desktop application without changing the core.

UI operations run through application services. Long ingestion runs execute in a worker thread/process and report progress without blocking the event loop.

### 13.1 Project Page

Shows:

- project name
- current snapshot
- document inventory
- current versions
- extraction statistics
- warnings

### 13.2 Document Page

Tabs:

- Overview
- Structure
- Tables
- Visuals
- Versions
- Raw metadata

### 13.3 Diff Page

Shows counts and field-level changes for semantic and presentation changes. Source locators link to the surrounding extracted context.

### 13.4 Search Page

Supports:

- query
- document and type filters
- current/historical scope
- result snippets
- source references
- token estimate
- context preview
- visual preview when relevant

### 13.5 Visuals Page

Supports:

- thumbnail or binary preview
- include/exclude retrieval
- mark decorative
- inspect source location
- edit optional generated summary

## 14. MCP Server

The MCP server exposes read-oriented agent tools by default:

- `list_projects`
- `list_documents`
- `search_documents`
- `get_block`
- `get_context`
- `get_table_rows`
- `list_visuals`
- `get_visual_metadata`
- `get_document_history`
- `diff_document_versions`

Mutation tools for ingest or snapshot acceptance may be enabled through configuration but are disabled by default to reduce accidental writes.

The MCP layer returns compact JSON and never embeds raw image binaries in ordinary search results.

## 15. Error Handling

Errors are separated into domain-level categories:

- unsupported format
- corrupt OOXML package
- encrypted document
- extraction failure
- storage failure
- version conflict
- invalid source replacement
- missing optional renderer
- resource limit exceeded

Behavior rules:

1. A failed ingest does not replace the current accepted version.
2. Database writes use a transaction.
3. Visual extraction failures become warnings when textual extraction can still succeed.
4. Unsupported structures produce warnings with source details.
5. The UI displays actionable messages and an ingest-run identifier.
6. CLI commands use non-zero exit codes and optionally emit structured error JSON.

## 16. Security and Privacy

The application is local-first and does not transmit document content by default.

- No external analysis is enabled without explicit configuration.
- Paths are normalized and constrained to project storage.
- ZIP extraction guards against path traversal and decompression bombs.
- Upload size, uncompressed size, XML size, and block count limits are configurable.
- SQLite queries use parameters.
- HTML previews escape source content.
- Visual binaries are served only from managed content-addressed paths.
- Secrets for future provider adapters are loaded from environment variables, never stored in the knowledge database.

## 17. Performance Targets

For a typical project containing several Office files and up to approximately 10,000 semantic blocks:

- unchanged file detection should complete in seconds, dominated by file hashing
- FTS search should normally complete below 200 ms on a local machine
- the search API should return at most the configured token/context budget
- replacing one small changed document should not rebuild indexes for unrelated documents
- unchanged blocks should not be re-indexed

The implementation uses streaming or read-only modes where compatible with fidelity requirements, while avoiding premature optimization that loses metadata.

## 18. Testing Strategy

### 18.1 Unit Tests

Cover:

- stable key creation
- semantic and presentation hashing
- display-value formatting helpers
- version matching and diff classification
- token estimation
- context budgeting
- source locator serialization

### 18.2 Extractor Contract Tests

Every extractor must prove that:

- it supports only declared file types
- it returns a valid normalized document
- every block has a source locator
- every block has semantic and presentation hashes
- visual references resolve to extracted visual records
- warnings are explicit

### 18.3 Integration Tests

Cover:

- XLSX formulas, cached values, merged cells, hidden rows, links, comments, images, and tables
- DOCX headings, paragraphs, lists, tables, links, headers/footers, and images
- PPTX slides, text boxes, tables, notes, images, and charts
- SQLite migrations and transactions
- FTS indexing and retrieval
- first ingest, unchanged ingest, incremental update, deletion, and history
- package export

### 18.4 Architecture Tests

Enforce that:

- `domain` imports no adapter or interface package
- `application` imports no NiceGUI, Typer, MCP, openpyxl, python-docx, python-pptx, or SQLite implementation
- interfaces depend on application ports/use cases, not extractor internals

### 18.5 End-to-End Tests

Use the CLI and a temporary project directory to ingest fixture documents, search, update a source, inspect diff, and export a package.

UI smoke tests verify route creation and core user workflows without depending on fragile pixel assertions.

## 19. Code Quality and Documentation

Tooling:

- Python 3.12
- `uv` for dependency and environment management
- Ruff for formatting and linting
- Pyright for strict static typing
- Pytest and coverage
- import-linter or explicit architecture tests
- pre-commit hooks

Documentation rules:

- Public modules, classes, protocols, and non-trivial functions receive docstrings.
- Comments explain invariants, source-format caveats, and reasons, not obvious syntax.
- OOXML workarounds cite the relevant package part or relationship behavior in nearby comments/tests.
- No unresolved `TODO`, `TBD`, or placeholder implementation is accepted on the main implementation branch.

## 20. Dependency Choices

Runtime dependencies:

- `pydantic`
- `openpyxl`
- `python-docx`
- `python-pptx`
- `lxml`
- `Pillow`
- `typer`
- `rich`
- `nicegui`
- an MCP Python SDK

Development dependencies:

- `pytest`
- `pytest-cov`
- `pyright`
- `ruff`
- `import-linter`
- `pre-commit`

Optional system dependency:

- LibreOffice for higher-fidelity document/slide previews. Its absence is non-fatal.

Dependencies are pinned through the lock file after implementation starts.

## 21. Implementation Sequence

The implementation will be split into reviewable vertical stages:

1. Repository scaffold, quality gates, domain model, and ports.
2. SQLite schema, repositories, migrations, and FTS5 search.
3. XLSX extractor and fidelity/contract fixtures.
4. DOCX extractor and fixtures.
5. PPTX extractor and fixtures.
6. Stable version matching, incremental update, history, and snapshots.
7. Filesystem visual store and package export.
8. CLI workflows.
9. NiceGUI UI.
10. MCP server.
11. End-to-end hardening, security limits, documentation, and release packaging.

Each stage begins with failing tests for its intended behavior and ends with lint, typing, tests, and architecture checks passing.

## 22. Acceptance Checklist

Implementation is complete only when all of the following are true:

- [ ] A user can create a project from the UI.
- [ ] A user can upload XLSX, DOCX, and PPTX files.
- [ ] Ingestion creates normalized blocks, visuals, source mappings, and a current snapshot.
- [ ] Search returns compact source-backed results.
- [ ] The UI displays estimated tokens for selected context.
- [ ] Re-uploading the same binary performs no extraction.
- [ ] Updating a source produces a correct incremental diff.
- [ ] Unchanged semantic blocks retain identity and are not re-indexed.
- [ ] Deleted content remains available in history.
- [ ] Visual assets are extracted and loaded on demand.
- [ ] CLI supports project, ingest, search, diff, history, export, UI, and MCP operations.
- [ ] MCP exposes the documented retrieval tools.
- [ ] The exported knowledge package contains manifest, SQLite, TSV tables, visuals, and source mapping.
- [ ] Security limits protect ZIP/XML ingestion and filesystem paths.
- [ ] Ruff, Pyright, Pytest, coverage, and architecture checks pass.
- [ ] README, architecture documentation, usage examples, and contributor instructions are complete.

## 23. Design Decision Summary

The selected approach is a **local-first Python ports-and-adapters application with SQLite FTS5, a NiceGUI UI, Typer CLI, and MCP interface**.

Alternatives considered:

1. **One Markdown file per source** — simple, but still expensive for agent context and weak for filtering/counting/versioning.
2. **Vector-database-first ingestion** — useful later, but introduces external infrastructure and makes exact structured queries harder. FTS5 and structured tables are a better default.
3. **Separate implementations for XLSX, DOCX, and PPTX** — easy to start but duplicates storage, versioning, search, UI, and agent integration. A shared normalized model gives better maintainability.

The selected design keeps source extraction format-specific while keeping versioning, retrieval, UI, CLI, and MCP format-agnostic.
