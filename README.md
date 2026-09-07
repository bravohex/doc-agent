# Doc Agent

Doc Agent turns `.xlsx`, `.docx`, `.pptx`, and `.pdf` files into a **local, source-traceable knowledge store** that software agents can query without loading whole documents into context.

It's built for RFPs, estimates, Fit & Gap sheets, migration inventories, architecture decks, specifications, and other document-heavy projects where repeated agent queries would otherwise burn tens of thousands of tokens per file.

## Why this exists

A generic `Office -> Markdown` conversion is fine for humans reading a file, but it still pushes agents toward loading entire documents. Doc Agent splits the problem into two layers instead:

1. **Fidelity layer** — preserve raw values, formulas, source locations, structure, and visuals exactly as they appear in the source.
2. **Retrieval layer** — index small semantic blocks in SQLite FTS5 and return only what's relevant.

So instead of sending a 50,000-token workbook to an agent to answer "Which MOG functions use PayPay?", the agent searches the local index and gets back only the matching rows, plus the sheet/range references they came from.

## Status

`0.1.x` is the first working implementation of the approved architecture. GitHub Actions is the release gate: formatting, linting, static typing, tests, coverage, and wheel build all have to pass.

## How it's organized

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
Adapters: XLSX / DOCX / PPTX / PDF / SQLite / filesystem
```

`domain` and `application` never depend on Office libraries, NiceGUI, MCP, or a concrete SQLite adapter — that boundary is enforced by an automated test (`tests/architecture/test_dependency_boundaries.py`), not just convention.

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full picture.

## Requirements

- Python 3.14+
- SQLite with FTS5 support (included in standard CPython builds on common platforms)

No external tooling is required to ingest documents. LibreOffice may be added later for rendered preview/page mapping, but extraction never depends on it.

## Install

With `uv`:

```bash
uv venv
uv pip install -e ".[dev]"
```

With plain pip:

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

The knowledge store lives beside the project it describes: `.working/` in the enclosing project, found by walking up from the current directory to the nearest `.git` or `pyproject.toml`. Outside of any project it falls back to `~/.doc-agent`. Add `.working/` to your project's `.gitignore`.

Point it somewhere else at any time:

```bash
export DOC_AGENT_HOME="$PWD/.doc-agent"
```

`doc-agent info` prints the resolved store path, the context budget, and the supported formats without creating anything.

The retrieval context budget defaults to 2000 estimated tokens and is configurable:

```bash
export DOC_AGENT_MAX_CONTEXT_TOKENS=4000
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
doc-agent ingest PROJECT_ID ./contract.pdf
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

SQLite is the source of truth in the export. Markdown and TSV are there for navigation, inspection, and lightweight agent access — not as a replacement for the database.

## Updating a source document

Re-ingesting a file with the same logical name in the same project updates that document automatically. You can also replace by document ID explicitly:

```bash
doc-agent ingest PROJECT_ID ./fitgap-new.xlsx --replace DOCUMENT_ID
```

What happens on update:

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

Every change is classified as one of:

- `added`
- `changed_semantic`
- `changed_presentation`
- `moved`
- `deleted`
- `unchanged`

Deleted blocks stay in historical versions but drop out of current search results.

## Fidelity rules

Doc Agent deliberately avoids "smart" transformations that would silently change what a source means.

For example, an Excel cell keeps all three of its values distinct instead of collapsing them into one:

```text
Excel raw value:      0.125
Excel number format:  0.0%
Readable display:     12.5%
```

Formula cells keep the formula and its cached value separate too:

```text
formula:       =B17/C17
cached_value:  0.125
```

`openpyxl` doesn't calculate formulas — the cached value comes from whatever application last saved the workbook, and it may be missing or stale.

Merged-cell values stay attached to the source top-left cell. Doc Agent doesn't fabricate duplicate raw values across every cell in the merged range.

## Visuals

Images are extracted into content-addressed storage and referenced by metadata — search results never inject image bytes into normal context.

Visuals can be:

- included in or excluded from retrieval metadata
- marked decorative
- given a human-written or optionally generated summary

By default, no project calls an external vision or OCR service.

## Local UI

```bash
doc-agent ui
```

Then open `http://127.0.0.1:8080`.

The UI covers project creation and selection, document upload, search, version history with what each version changed, and visual curation. Search results name where each hit came from, in terms native to its format — `Sheet MOG · row 12`, `Page 3`, `Slide 2 · Title 1` — and show what retrieving all of them would cost in tokens. Extraction warnings from an ingest are surfaced rather than dropped, and expected failures show up as a notice instead of a stack trace in the terminal.

The UI calls the same application services as the CLI and MCP server — it doesn't parse documents itself. Everything it displays is shaped by `interfaces/ui/presenter.py`, which has no NiceGUI import and is unit tested, so the page itself stays thin, declarative wiring.

## MCP

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

## Feature summary

- **XLSX** — raw vs. display values, formulas vs. cached values, number formats, comments, hyperlinks, merged ranges, hidden row/column metadata, defined table metadata, compact row-level retrieval blocks, embedded images and basic charts
- **DOCX** — document-order paragraphs and tables, heading hierarchy, list/style metadata, hyperlinks, headers and footers, embedded images
- **PPTX** — slide containers and titles, text boxes and tables, speaker notes, shape identifiers and bounds, images and chart series, a `visual_required` signal for spatial/diagram-heavy slides
- **PDF** — page containers with paragraph blocks in reading order, ruled tables as row blocks (not repeated prose), page/bounding-box/font-size kept per block, embedded images decoded back to original bytes, pages without extractable text reported rather than silently emptied
- **Retrieval** — SQLite + FTS5 search, source locators on every result, estimated retrieval-token cost, content-addressed visual storage, version history with incremental updates, semantic vs. presentation change classification, collection snapshots after ingestion, portable export packages
- **Interfaces** — Typer CLI, local NiceGUI UI, read-oriented MCP server
- **Safety** — OOXML ZIP safety limits, automated architecture boundary tests

## Current limitations

This is an extraction and retrieval system, not an Office renderer or editor.

- no perfect Office round-trip reconstruction
- no heading hierarchy for PDF, because the format doesn't record one
- no mandatory vector database
- no automatic OCR
- no guaranteed semantic reconstruction for every SmartArt or arbitrary drawing graph
- DOCX page number is not treated as stable identity
- formula evaluation is not performed by Python
- source display formatting is best-effort when Office-specific formatting can't be represented exactly

These are explicit extension points, not hidden gaps.

## Design documents

- [Architecture/product design](docs/superpowers/specs/2026-09-03-doc-agent-design.md)
- [Implementation plan](docs/superpowers/plans/2026-09-03-doc-agent-implementation.md)
