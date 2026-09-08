# Doc Agent

**Local-first knowledge packages for retrieval-efficient agents.**

[![CI](https://github.com/bravohex/doc-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/bravohex/doc-agent/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.14%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](#license)

Doc Agent converts `.xlsx`, `.docx`, `.pptx`, and `.pdf` files into a local, source-traceable knowledge store that software agents can query without loading entire documents into context.

It targets document-heavy engagements — RFPs, estimates, Fit & Gap sheets, migration inventories, architecture decks, and specifications — where repeated agent queries against raw files would otherwise consume tens of thousands of tokens per request.

---

## Contents

- [Motivation](#motivation)
- [Capabilities](#capabilities)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Installation](#installation)
- [Getting started](#getting-started)
- [CLI reference](#cli-reference)
- [Pausing and deleting](#pausing-and-deleting)
- [Versioning and updates](#versioning-and-updates)
- [Fidelity guarantees](#fidelity-guarantees)
- [Visual assets](#visual-assets)
- [Local UI](#local-ui)
- [MCP server](#mcp-server)
- [Development](#development)
- [Limitations](#limitations)
- [Documentation](#documentation)
- [License](#license)

---

## Motivation

Generic `Office → Markdown` conversion serves human readers, but it still encourages agents to load whole documents. Doc Agent separates the problem into two layers:

| Layer | Responsibility |
| --- | --- |
| **Fidelity** | Preserve raw values, formulas, source locations, structure, and visuals exactly as recorded in the source. |
| **Retrieval** | Index small semantic blocks in SQLite FTS5 and return only the matching context. |

To answer a question such as *"Which MOG functions use PayPay?"*, an agent queries the local index and receives the matching rows together with their originating sheet and range — not a 50,000-token workbook.

## Capabilities

### Format coverage

| Format | Extracted content |
| --- | --- |
| **XLSX** | Raw and display values held separately; formulas and cached formula values held separately; number formats, comments, hyperlinks, merged ranges; hidden row/column metadata; defined table metadata; data-validation and conditional-formatting rules with the ranges they cover; defined names; the workbook's calculation mode; frozen panes, filters, sheet protection and hidden rows/columns; sparse cell styling (emphasis, strikethrough, colours, unlocked cells); compact row-level retrieval blocks; embedded images and basic charts. |
| **DOCX** | Document-order paragraphs and tables; heading hierarchy; list and style metadata; hyperlinks; headers and footers; embedded images. |
| **PPTX** | Slide containers and titles; text boxes and tables; speaker notes; shape identifiers and bounds; images and chart series; a `visual_required` signal for spatial or diagram-heavy slides. |
| **PDF** | Page containers with paragraph blocks in reading order; ruled tables as row blocks rather than repeated prose; page, bounding box, and font size retained per block; embedded images decoded to their original bytes; pages without extractable text reported explicitly rather than returned as empty. |

### Platform

- SQLite + FTS5 full-text search with a source locator on every result
- Cell-addressed reads (`sheet` + A1 `range`) with pagination, so a few cells cost a few cells
- Workbook audit metadata: validation rules, conditional rules, defined names, calculation mode
- Selective formatting: frozen panes, filters, protection, hidden rows and columns, and the cell styling that carries meaning
- Estimated retrieval-token cost reported per result set
- Content-addressed visual storage
- Immutable version history with incremental updates, and reads pinnable to one version
- Documents can be paused, excluding a stale source from retrieval without deleting it
- Semantic versus presentation change classification
- Project snapshots created after each successful ingestion
- Portable export packages
- Typer CLI, local NiceGUI UI, and a read-oriented MCP server
- OOXML ZIP safety limits
- Architecture boundaries enforced by automated tests

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
Adapters: XLSX / DOCX / PPTX / PDF / SQLite / filesystem
```

The `domain` and `application` layers never depend on Office libraries, NiceGUI, MCP, or a concrete SQLite adapter. This dependency rule is verified by `tests/architecture/test_dependency_boundaries.py` rather than left to convention.

Full details: [ARCHITECTURE.md](ARCHITECTURE.md).

## Requirements

- Python 3.14 or later
- SQLite with FTS5 support (present in standard CPython builds on common platforms)

No external tooling is required for ingestion. LibreOffice may be introduced later for rendered preview and page mapping, but extraction does not depend on it.

## Installation

Using `uv`:

```bash
uv venv
uv pip install -e ".[dev]"
```

Using `pip`:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

### Launcher script

`run.sh` starts the interfaces and provisions the virtualenv on first run, so no separate install step is required:

```bash
./run.sh              # UI at / and HTTP MCP at /mcp, one process on port 8080
./run.sh --port 9000  # same, on another port
./run.sh ui           # UI only
./run.sh mcp          # stdio MCP only
```

The default mode is [`serve`](#serving-the-ui-and-mcp-together): one command for both audiences.

## Getting started

### 1. Confirm the store location

The knowledge store lives beside the work it describes: `.working/` inside the enclosing project, located by walking up from the current directory to the nearest `.git` or `pyproject.toml`. Outside any project, it falls back to `~/.doc-agent`. Add `.working/` to the project's `.gitignore`.

`doc-agent info` reports the resolved store, the context budget, and the supported formats without creating anything.

| Variable | Default | Purpose |
| --- | --- | --- |
| `DOC_AGENT_HOME` | `.working/` in the enclosing project, else `~/.doc-agent` | Override the knowledge store location. |
| `DOC_AGENT_MAX_CONTEXT_TOKENS` | `2000` | Retrieval context budget, in estimated tokens. |

```bash
export DOC_AGENT_HOME="$PWD/.doc-agent"
export DOC_AGENT_MAX_CONTEXT_TOKENS=4000
```

### 2. Create a project

```bash
doc-agent project create "OLM Shopify Plus"
doc-agent project list
```

### 3. Ingest documents

Use the project ID returned above:

```bash
doc-agent ingest PROJECT_ID ./RFP.docx
doc-agent ingest PROJECT_ID ./fitgap.xlsx
doc-agent ingest PROJECT_ID ./architecture.pptx
doc-agent ingest PROJECT_ID ./contract.pdf
```

### 4. Search and retrieve

```bash
doc-agent search PROJECT_ID "PayPay"
doc-agent search PROJECT_ID "rollback OR ロールバック" --limit 50 --json
doc-agent get BLOCK_ID
```

### 5. Export a portable package

```bash
doc-agent export PROJECT_ID ./knowledge-export
```

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

SQLite is the authoritative source within the package. The Markdown and TSV artifacts exist for navigation, inspection, and lightweight agent access — they do not replace the database.

## CLI reference

| Command | Description |
| --- | --- |
| `doc-agent info` | Report the resolved store, context budget, and supported formats. |
| `doc-agent project create NAME` | Create a knowledge project. |
| `doc-agent project list` | List projects. |
| `doc-agent project show PROJECT_ID` | Show a single project. |
| `doc-agent ingest PROJECT_ID SOURCE [--replace DOCUMENT_ID]` | Ingest or re-ingest a document. |
| `doc-agent documents PROJECT_ID` | List documents, with each one's retrieval state. |
| `doc-agent pause DOCUMENT_ID` | Stop retrieval reading a document, keeping its versions. |
| `doc-agent resume DOCUMENT_ID` | Let retrieval read a paused document again. |
| `doc-agent delete DOCUMENT_ID [--yes]` | Delete a document, its versions, and its history. |
| `doc-agent search PROJECT_ID QUERY [--limit N] [--json]` | Full-text search; defaults to 20 results. |
| `doc-agent get BLOCK_ID` | Retrieve a single block. |
| `doc-agent history DOCUMENT_ID` | Show version history. |
| `doc-agent diff DOCUMENT_ID --version N` | Show classified changes for a version. |
| `doc-agent export PROJECT_ID DESTINATION` | Write a portable knowledge package. |
| `doc-agent serve [--host H] [--port P] [--mcp-path /mcp]` | Serve the UI and an HTTP MCP endpoint from one process. |
| `doc-agent ui [--host H] [--port P]` | Start the local NiceGUI interface. |
| `doc-agent mcp` | Start the read-oriented MCP server on stdio. |

## Pausing and deleting

A stale source does not have to be discarded. Pausing a document keeps every version
and its history but withholds it from retrieval, so searches stop returning it and it
can be resumed later:

```bash
doc-agent pause DOCUMENT_ID
doc-agent resume DOCUMENT_ID
```

Deleting is for a document that should leave no trace, and cannot be undone:

```bash
doc-agent delete DOCUMENT_ID
```

Both are also in the UI, on each row of the library. Deleting removes the document's
versions, history, change log, and search entries. Extracted images are content-addressed
and shared, so only those no document still references are removed from storage.

Pausing changes retrieval, not the record. A paused document stays listed, keeps its
history and diffs, and reports itself rather than returning empty content when
retrieval targets it directly — empty results would be indistinguishable from a
document that genuinely holds nothing.

## Versioning and updates

Re-ingesting a file with the same logical name in the same project updates that document. A document may also be replaced explicitly by ID:

```bash
doc-agent ingest PROJECT_ID ./fitgap-new.xlsx --replace DOCUMENT_ID
```

Update pipeline:

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

Each block change is classified as `added`, `changed_semantic`, `changed_presentation`, `moved`, `deleted`, or `unchanged`. Deleted blocks remain available in historical versions but are removed from current search results.

Identity is derived from content rather than physical position, so inserting a worksheet row does not mark every subsequent block as new. See [docs/STABLE_IDENTITY.md](docs/STABLE_IDENTITY.md).

## Fidelity guarantees

Doc Agent avoids transformations that would silently alter source meaning.

An Excel cell retains all three representations rather than collapsing them:

```text
Excel raw value:      0.125
Excel number format:  0.0%
Readable display:     12.5%
```

Formula cells retain the formula and its cached value separately:

```text
formula:       =B17/C17
cached_value:  0.125
```

`openpyxl` does not evaluate formulas. Cached values originate from the application that last saved the workbook and may be absent or stale.

Rather than leaving that to be inferred, every cell read through the MCP server carries a
`value_state` (`literal`, `cached`, `uncalculated`) and a `display_state` (`exact`,
`normalized`, `approximate`, `unavailable`). A `#,##0.00` cell displaying `1234567.891`
where the sheet shows `1,234,567.89` reports `approximate`; a formula with no saved result
reports `uncalculated` rather than an empty string that reads like an empty cell. See
[docs/MCP.md](docs/MCP.md).

Merged-cell values remain attached to the source top-left cell; Doc Agent does not fabricate duplicate raw values across the merged range.

## Visual assets

Images are extracted into content-addressed storage and referenced by metadata. Search results never inject image bytes into ordinary context.

Each visual can be included in or excluded from retrieval metadata, marked as decorative, and annotated with a human-written or optionally generated summary. No external vision or OCR service is called by default.

## Local UI

```bash
doc-agent ui
```

The interface is served at `http://127.0.0.1:8080` and covers project creation and selection, document upload, search, version history with per-version changes, and visual curation.

Search results identify each hit in terms native to its format — `Sheet MOG · row 12`, `Page 3`, `Slide 2 · Title 1` — and state the token cost of retrieving the full result set. Extraction warnings are surfaced rather than discarded, and expected failures are presented as notices instead of terminal stack traces.

The UI consumes the same application services as the CLI and MCP server and never parses documents directly. All displayed data is shaped by `interfaces/ui/presenter.py`, which imports no NiceGUI symbols and is unit tested, keeping the page itself declarative wiring.

## MCP server

The server exposes read-oriented tools only; mutation tools are deliberately withheld. Two transports are available, with identical tools.

### Serving the UI and MCP together

```bash
doc-agent serve
```

One process serves the UI at `http://127.0.0.1:8080` for a person and an HTTP MCP endpoint at `http://127.0.0.1:8080/mcp` for agents. This is the mode to use when you work in the UI while agents query the same store, since a stdio server cannot be shared — clients spawn their own copy of it.

```json
{ "mcpServers": { "doc-agent": { "type": "http", "url": "http://127.0.0.1:8080/mcp" } } }
```

The endpoint binds to localhost and is unauthenticated; `--host 0.0.0.0` exposes the entire knowledge store to anything that can reach the port.

### stdio

```bash
doc-agent mcp
```

For clients that spawn the server themselves. See [docs/MCP.md](docs/MCP.md) for registration and the full tool contract.

### Tools

| Tool | Purpose |
| --- | --- |
| `list_projects` | Enumerate knowledge projects. |
| `list_documents` | Enumerate documents in a project. |
| `search_documents` | Full-text search within a project. |
| `get_block` | Retrieve a single block by ID. |
| `get_context` | Retrieve multiple blocks within a token budget, at `text`/`cells`/`full` detail. |
| `describe_workbook` | Calculation mode, defined names, per-sheet summary. Read this first when auditing. |
| `list_sheets` | Per sheet: order, hidden state, extent, tables, validation and conditional rules, layout. |
| `get_sheet_range` | Read cells by A1 address (`MOG!B2:D10`), paged, with per-cell trust states. |
| `get_table_rows` | Retrieve a page of table rows for a document. |
| `list_visuals` | List visual metadata for a document. |
| `document_history` | Retrieve version history. |
| `diff_document_version` | Retrieve classified changes for a version. |

Parameters, return shapes, query syntax, and the retrieval workflow agents should follow are documented in [docs/MCP.md](docs/MCP.md); broader agent guidance is in [docs/USAGE.md](docs/USAGE.md).

## Development

`0.1.x` is the first working implementation of the approved architecture. GitHub Actions is the authoritative release gate; formatting, linting, static typing, tests, coverage, and the wheel build must all pass.

```bash
python -m ruff format --check .
python -m ruff check .
python -m pyright
python -m pytest --cov=doc_agent --cov-report=term-missing --cov-fail-under=80
```

Contribution guidelines: [CONTRIBUTING.md](CONTRIBUTING.md).

## Limitations

Doc Agent is an extraction and retrieval system, not an Office renderer or editor.

- No lossless Office round-trip reconstruction
- No heading hierarchy for PDF, as the format does not record one
- No mandatory vector database
- No automatic OCR
- No guaranteed semantic reconstruction of every SmartArt or arbitrary drawing graph
- DOCX page number is not treated as stable identity
- Formula evaluation is not performed in Python
- Source display formatting is best-effort where Office-specific formatting cannot be represented exactly

These are documented extension points, not undisclosed behavior.

## Documentation

| Document | Contents |
| --- | --- |
| [ARCHITECTURE.md](ARCHITECTURE.md) | Layer responsibilities and the dependency rule. |
| [docs/MCP.md](docs/MCP.md) | MCP tool contract: transports, parameters, return shapes, query syntax, token budget. |
| [docs/USAGE.md](docs/USAGE.md) | Retrieval-first agent workflow and visual-inspection guidance. |
| [docs/STABLE_IDENTITY.md](docs/STABLE_IDENTITY.md) | Stable block identity across document versions. |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Development workflow and review expectations. |
| [Architecture / product design](docs/superpowers/specs/2026-09-03-doc-agent-design.md) | Approved design specification. |
| [Implementation plan](docs/superpowers/plans/2026-09-03-doc-agent-implementation.md) | Phased implementation plan. |

## License

Released under the MIT License.
