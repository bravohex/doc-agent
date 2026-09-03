# Doc Agent

Doc Agent turns `.xlsx`, `.docx`, and `.pptx` files into a **local, source-traceable knowledge store** that software agents can query without loading entire Office documents into context.

The project is designed for RFPs, estimates, Fit & Gap sheets, migration inventories, architecture decks, specifications, and other document-heavy projects where repeated agent queries would otherwise consume tens of thousands of tokens.

## Why this exists

A generic `Office -> Markdown` conversion is useful for reading, but it still encourages agents to load large files. Doc Agent separates the problem into two layers:

1. **Fidelity layer** — preserve raw values, formulas, source locations, structure, and visuals.
2. **Retrieval layer** — index small semantic blocks in SQLite FTS5 and return only relevant context.

For example, instead of sending a 50,000-token workbook to an agent to answer “Which MOG functions use PayPay?”, the agent searches the local index and receives only matching rows plus their original sheet/range references.

## Features

- XLSX extraction
  - raw values and display values are separate
  - formulas and cached formula values are separate
  - number formats, comments, hyperlinks, merged ranges
  - hidden row/column metadata
  - defined Excel table metadata
  - compact row-level retrieval blocks
  - embedded image and basic chart extraction
- DOCX extraction
  - document-order paragraphs and tables
  - heading hierarchy
  - list/style metadata
  - hyperlinks
  - headers and footers
  - embedded images
- PPTX extraction
  - slide containers and titles
  - text boxes and tables
  - speaker notes
  - shape identifiers and bounds
  - images and chart series
  - `visual_required` signal for spatial/diagram-heavy slides
- SQLite + FTS5 search
- source locators in every search result
- estimated retrieval-token cost
- content-addressed visual storage
- version history and incremental update
- semantic vs presentation change classification
- collection snapshots after successful ingestion
- portable export package
- Typer CLI
- local NiceGUI UI
- read-oriented MCP server
- OOXML ZIP safety limits
- automated architecture boundary tests

## Architecture

```text
UI / CLI / MCP
       |
       v
Application use cases
       |
       v
Domain + ports
       ^
       |
Adapters: XLSX / DOCX / PPTX / SQLite / filesystem
```

`domain` and `application` never depend on Office libraries, NiceGUI, MCP, or concrete SQLite adapters. The dependency rule is enforced by `tests/architecture/test_dependency_boundaries.py`.

See [ARCHITECTURE.md](ARCHITECTURE.md) for details.

## Requirements

- Python 3.12+
- SQLite with FTS5 support (included in standard CPython builds on common platforms)

Optional external tooling is **not required** to ingest documents. LibreOffice may be added later for rendered preview/page mapping, but extraction does not depend on it.

## Installation

Using `uv`:

```bash
uv venv
uv pip install -e ".[dev]"
```

Or standard pip:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

On Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## Quick start

Set a local data directory if you do not want the default `~/.doc-agent`:

```bash
export DOC_AGENT_HOME="$PWD/.doc-agent"
```

Create a project:

```bash
doc-agent project create "OLM Shopify Plus"
doc-agent project list
```

Use the returned project ID to ingest documents:

```bash
doc-agent ingest PROJECT_ID ./RFP.docx
doc-agent ingest PROJECT_ID ./fitgap.xlsx
doc-agent ingest PROJECT_ID ./architecture.pptx
```

Search:

```bash
doc-agent search PROJECT_ID "PayPay"
doc-agent search PROJECT_ID "rollback OR ロールバック" --json
```

Inspect documents and versions:

```bash
doc-agent documents PROJECT_ID
doc-agent history DOCUMENT_ID
doc-agent diff DOCUMENT_ID --version 2
```

Export a portable knowledge package:

```bash
doc-agent export PROJECT_ID ./knowledge-export
```

The export contains:

```text
knowledge-export/
├── MANIFEST.md
├── manifest.json
├── knowledge.sqlite
├── source-map.jsonl
├── tables/
│   └── *.tsv
└── visuals/
```

SQLite remains the authoritative data source. Markdown and TSV exist for navigation, inspection, and lightweight agent access.

## Updating a source document

If the source file has the same logical name in the same project, normal ingest updates that document. You can also explicitly replace by document ID:

```bash
doc-agent ingest PROJECT_ID ./fitgap-new.xlsx --replace DOCUMENT_ID
```

Update behavior:

```text
hash identical
  -> skip extraction

hash changed
  -> extract
  -> compare stable blocks
  -> persist immutable version
  -> classify changes
  -> replace only that document's FTS entries
  -> create a new project snapshot
```

Changes are classified as:

- `added`
- `changed_semantic`
- `changed_presentation`
- `moved`
- `deleted`
- `unchanged`

Deleted blocks remain in historical versions but disappear from current search.

## Fidelity rules

Doc Agent intentionally avoids “smart” transformations that would silently change source meaning.

Examples:

```text
Excel raw value:      0.125
Excel number format:  0.0%
Readable display:     12.5%
```

All three are kept separately.

For formula cells:

```text
formula:       =B17/C17
cached_value:  0.125
```

`openpyxl` does not calculate formulas; cached values come from the application that last saved the workbook and may be absent or stale.

Merged-cell values stay attached to the source top-left cell. Doc Agent does not fabricate duplicate raw values into every cell of the merged range.

## Visuals

Images are extracted to content-addressed storage and referenced by metadata. Search results do not inject image bytes into normal context.

Visuals can be:

- included/excluded from retrieval metadata
- marked decorative
- given a human or optional generated summary

The default project does **not** call an external vision or OCR service.

## Local UI

Run:

```bash
doc-agent ui
```

Then open `http://127.0.0.1:8080`.

The first UI supports project creation, document upload, search, version inventory, change counts, and visual inventory. It uses the same application services as CLI and MCP; it does not parse Office files directly.

## MCP

Run:

```bash
doc-agent mcp
```

Read-oriented tools include:

- project/document listing
- search
- get block/context
- get table rows
- visual metadata listing
- version history
- version diff

Mutation tools are intentionally not exposed by default.

## Development

```bash
python -m ruff format --check .
python -m ruff check .
python -m pyright
python -m pytest --cov=doc_agent --cov-report=term-missing --cov-fail-under=80
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Current limitations

This is an extraction and retrieval system, not an Office renderer or editor.

- no perfect Office round-trip reconstruction
- no PDF extractor yet
- no mandatory vector database
- no automatic OCR
- no guaranteed semantic reconstruction for every SmartArt or arbitrary drawing graph
- DOCX page number is not treated as stable identity
- formula evaluation is not performed by Python
- source display formatting is best-effort when Office-specific formatting cannot be represented exactly

These are explicit extension points rather than hidden behavior.

## Design documents

- [Architecture/product design](docs/superpowers/specs/2026-09-03-doc-agent-design.md)
- [Implementation plan](docs/superpowers/plans/2026-09-03-doc-agent-implementation.md)
