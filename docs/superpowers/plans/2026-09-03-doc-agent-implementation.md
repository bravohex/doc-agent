# Doc Agent — Full Implementation Plan

Date: 2026-09-03
Branch: `feat/full-doc-agent-implementation`
Design: `docs/superpowers/specs/2026-09-03-doc-agent-design.md`

## Delivery strategy

Implement in vertical, test-first stages. Each stage begins with a behavioral test that fails for the intended reason, adds the minimum production code to pass, and then refactors while keeping all checks green.

## Task 1 — Repository foundation and quality gates

Create:

- `pyproject.toml`
- `.gitignore`
- `.pre-commit-config.yaml`
- `.github/workflows/ci.yml`
- `README.md`
- `ARCHITECTURE.md`
- `CONTRIBUTING.md`
- `src/doc_agent/__init__.py`
- `src/doc_agent/settings.py`
- `tests/architecture/test_dependency_boundaries.py`

Acceptance:

- Python package imports under Python 3.12.
- Ruff, Pyright, and Pytest are configured.
- Architecture test rejects forbidden adapter/framework imports from `domain` and `application`.

Verification:

```bash
python -m pytest tests/architecture -q
python -m ruff check .
python -m pyright
```

## Task 2 — Domain model, IDs, hashing, and token budgets

Create:

- `src/doc_agent/domain/models.py`
- `src/doc_agent/domain/identifiers.py`
- `src/doc_agent/domain/hashing.py`
- `src/doc_agent/domain/errors.py`
- `src/doc_agent/adapters/tokens/heuristic.py`
- `src/doc_agent/ports/tokens.py`
- unit tests under `tests/unit/domain/` and `tests/unit/tokens/`

Acceptance:

- Source locators serialize deterministically.
- Semantic and presentation hashes change independently.
- Stable keys are deterministic and do not use ordinals as the sole identity.
- Token-budget trimming never returns context above its configured budget.

## Task 3 — Ports and extractor registry

Create:

- `src/doc_agent/ports/extractors.py`
- `src/doc_agent/ports/repositories.py`
- `src/doc_agent/ports/search.py`
- `src/doc_agent/ports/visuals.py`
- `src/doc_agent/ports/clocks.py`
- `src/doc_agent/adapters/extractors/registry.py`
- contract tests under `tests/contract/`

Acceptance:

- Registry chooses the correct extractor by suffix.
- Unsupported formats raise a typed domain error.
- All extractors return a normalized document satisfying the shared contract.

## Task 4 — Safe OOXML package inspection and visual store

Create:

- `src/doc_agent/adapters/extractors/ooxml.py`
- `src/doc_agent/adapters/filesystem/visual_store.py`
- `src/doc_agent/adapters/visuals/null_analyzer.py`
- tests under `tests/unit/ooxml/` and `tests/integration/filesystem/`

Acceptance:

- Reject path traversal, excessive entry counts, and excessive uncompressed sizes.
- Resolve package media and relationship targets safely.
- Store visual blobs by SHA-256 and deduplicate identical binaries.

## Task 5 — XLSX extractor

Create:

- `src/doc_agent/adapters/extractors/xlsx.py`
- dynamically generated fixtures in `tests/fixtures/builders.py`
- `tests/integration/extractors/test_xlsx.py`

Acceptance:

- Preserve raw values, formulas, cached values when available, data types, formats, hyperlinks, comments, hidden rows/columns, merged ranges, sheet visibility, and source cell/range locators.
- Keep merged-cell raw values only at the top-left source cell.
- Index compact non-empty row blocks.
- Extract embedded images and basic chart metadata without requiring OCR.

## Task 6 — DOCX extractor

Create:

- `src/doc_agent/adapters/extractors/docx.py`
- `tests/integration/extractors/test_docx.py`

Acceptance:

- Preserve document order for paragraphs and tables.
- Track heading hierarchy, list/style metadata, hyperlinks, headers, footers, tables, rows, images, and source locators.
- Do not treat rendered page number as a stable identity.

## Task 7 — PPTX extractor

Create:

- `src/doc_agent/adapters/extractors/pptx.py`
- `tests/integration/extractors/test_pptx.py`

Acceptance:

- Preserve slide containers, title, text boxes, tables, speaker notes, shape identifiers/bounds, images, and chart series when exposed by the library.
- Mark spatial/diagram slides as requiring visual inspection.

## Task 8 — SQLite schema, repositories, and FTS5

Create:

- `src/doc_agent/adapters/sqlite/connection.py`
- `src/doc_agent/adapters/sqlite/migrations.py`
- `src/doc_agent/adapters/sqlite/repository.py`
- `src/doc_agent/adapters/sqlite/search_index.py`
- integration tests under `tests/integration/sqlite/`

Acceptance:

- Transactional schema migration and persistence.
- Current and historical document/version/block/visual/change records.
- FTS5 search with project/document filters, bounded snippets, stable-key exact lookup, and source locators.
- Presentation-only changes do not force semantic re-indexing.

## Task 9 — Version differ, incremental ingest, snapshots, and retrieval

Create:

- `src/doc_agent/application/projects.py`
- `src/doc_agent/application/ingest.py`
- `src/doc_agent/application/diff.py`
- `src/doc_agent/application/history.py`
- `src/doc_agent/application/search.py`
- `src/doc_agent/application/retrieve.py`
- `src/doc_agent/bootstrap.py`
- unit/integration tests for first ingest, unchanged ingest, semantic change, presentation-only change, move, addition, deletion, rollback on failure, and current snapshot behavior.

Acceptance:

- Identical source hash skips extraction.
- Modified files generate a new version and field-level change records.
- Unchanged stable blocks retain identity.
- Deleted blocks remain queryable in history but not current search.
- Failed ingest never replaces the current accepted version.

## Task 10 — Portable package export

Create:

- `src/doc_agent/application/export.py`
- `src/doc_agent/adapters/export/package.py`
- `tests/integration/export/test_package.py`

Acceptance:

- Export `MANIFEST.md`, `manifest.json`, `knowledge.sqlite`, TSV tables, visual assets, and `source-map.jsonl`.
- Manifests remain compact navigation aids; SQLite remains authoritative.

## Task 11 — CLI

Create:

- `src/doc_agent/interfaces/cli.py`
- CLI tests under `tests/integration/cli/`

Commands:

- `project create/list/show`
- `ingest`
- `documents`
- `search`
- `get`
- `history`
- `diff`
- `export`
- `ui`
- `mcp`

Acceptance:

- Human-readable default output and JSON output where useful.
- Typed errors produce non-zero exits without stack traces in normal mode.

## Task 12 — NiceGUI local UI

Create:

- `src/doc_agent/interfaces/ui/app.py`
- `src/doc_agent/interfaces/ui/dependencies.py`
- UI pages/components under `src/doc_agent/interfaces/ui/`
- UI service/smoke tests under `tests/unit/ui/`

Acceptance:

- Create/open projects.
- Upload new documents or replace an existing logical document.
- Show ingestion progress, versions, warnings, changes, document structure, visuals, and retrieval search.
- Display estimated context tokens.
- UI imports and invokes application services rather than extractor/SQLite internals.

## Task 13 — MCP server

Create:

- `src/doc_agent/interfaces/mcp_server.py`
- tests under `tests/unit/mcp/`

Read tools:

- list projects/documents
- search documents
- get block/context/table rows
- list/get visual metadata
- document history
- version diff

Acceptance:

- Compact JSON responses.
- Mutation tools disabled by default.
- Missing optional MCP dependency produces an actionable runtime message rather than breaking normal package imports.

## Task 14 — End-to-end hardening and release verification

Create/update:

- `tests/e2e/test_office_project_workflow.py`
- usage examples and troubleshooting documentation
- security/resource-limit tests

End-to-end scenario:

1. Create a project.
2. Generate and ingest XLSX, DOCX, and PPTX fixtures.
3. Search across all three.
4. Modify the XLSX source and re-ingest it as a replacement.
5. Verify incremental diff and history.
6. Export a portable package.

Final verification:

```bash
python -m ruff format --check .
python -m ruff check .
python -m pyright
python -m pytest --cov=doc_agent --cov-report=term-missing --cov-fail-under=80
```

Completion also requires a self-review of the final diff and a pull request summarizing architecture, supported formats, limitations, test evidence, and follow-up extension points.
