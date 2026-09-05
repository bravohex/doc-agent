# Contributing

## Principles

- Preserve source meaning before optimizing readability.
- Do not silently invent Office semantics.
- Keep source locators with every extracted block.
- Prefer small ports and focused adapters over “manager” classes.
- UI, CLI, and MCP must reuse application services.
- Comments explain **why**, invariants, or source-format caveats; they do not restate obvious code.

## Setup

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
pre-commit install
```

## TDD workflow

For behavior changes:

1. Add one focused failing test.
2. Run it and confirm failure is caused by missing behavior.
3. Implement the minimum change.
4. Run the focused test.
5. Run the full suite.
6. Refactor only while green.

## Quality gates

```bash
python -m ruff format --check .
python -m ruff check .
python -m pyright
python -m pytest --cov=doc_agent --cov-report=term-missing --cov-fail-under=80
```

## Source-format comments

Good:

```python
# openpyxl does not calculate formulas. Cached values come from the
# spreadsheet application that last saved this workbook.
```

Bad:

```python
# Loop through rows.
for row in rows:
    ...
```

## Adding an extractor

An extractor must:

- explicitly declare supported suffixes
- return `ExtractedDocument`
- assign a source locator to every block/visual
- avoid ordinal-only stable identity
- expose unsupported structures as warnings rather than fabricated content
- pass extractor contract/integration tests

## Architecture boundaries

Never import these from `domain` or `application`:

- `openpyxl`
- `docx`
- `pptx`
- `pdfplumber`
- `pypdf`
- `sqlite3`
- `nicegui`
- MCP SDK
- any `doc_agent.adapters.*` module

The composition root is the intentional exception.
