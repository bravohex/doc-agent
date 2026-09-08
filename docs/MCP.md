# MCP server reference

Doc Agent exposes its knowledge store to agents through a read-oriented MCP server, over HTTP or stdio. This document is the contract: what each tool accepts, what it returns, and how to query the store without defeating its purpose.

- [Guarantees](#guarantees)
- [Registration](#registration)
- [The retrieval contract](#the-retrieval-contract)
- [Tool reference](#tool-reference)
- [Reading one version](#reading-one-version)
- [Cell fidelity](#cell-fidelity)
- [Field reference](#field-reference)
- [Query syntax](#query-syntax)
- [Token budget and truncation](#token-budget-and-truncation)
- [Errors](#errors)
- [Anti-patterns](#anti-patterns)

## Guarantees

| Guarantee | Detail |
| --- | --- |
| Read-only | No tool creates, mutates, or deletes anything. Ingestion is CLI- and UI-only by design. |
| No image bytes | Visual tools return metadata and a stored path. Image bytes never enter the response. |
| Current version by default, pinnable | Reads resolve against the document's **current** version unless `version_id` is passed. Every paged response reports the `version_id` it read and whether that `is_current_version`. |
| Paused documents withheld | A document can be paused in the UI or CLI. It stays in `list_documents` with `active: false`, never appears in search, and reports itself as paused if retrieval targets it directly. |
| Source-traceable | Every block and search result carries a `source` locator expressed in its own format's terms. |
| Bounded context | `get_context` never exceeds the configured token budget. |

## Registration

There are two transports. Both expose exactly the same twelve tools.

### HTTP — shared, alongside the UI

`doc-agent serve` runs one process that serves the UI at `/` for a person and the MCP endpoint at `/mcp` for agents, on one port:

```bash
doc-agent serve                      # UI http://127.0.0.1:8080, MCP http://127.0.0.1:8080/mcp
doc-agent serve --port 9000 --mcp-path /agent
```

```json
{
  "mcpServers": {
    "doc-agent": {
      "type": "http",
      "url": "http://127.0.0.1:8080/mcp"
    }
  }
}
```

Use this when a human is working in the UI while agents query the same store, or when several clients should share one process. The store is chosen by the environment the server was started in, so run it from the project (or with `DOC_AGENT_HOME` set) and the clients need no path configuration at all.

The endpoint binds to `127.0.0.1` by default and carries no authentication. Treat `--host 0.0.0.0` as exposing the whole knowledge store, unauthenticated, to anything that can reach the port.

### stdio — private, spawned per client

`doc-agent mcp` speaks JSON-RPC over stdio and is spawned by the client; it is not a daemon to connect to, and running it in a terminal by hand only looks idle.

```json
{
  "mcpServers": {
    "doc-agent": {
      "command": "/absolute/path/to/.venv/bin/doc-agent",
      "args": ["mcp"],
      "env": {
        "DOC_AGENT_HOME": "/absolute/path/to/project/.working",
        "DOC_AGENT_MAX_CONTEXT_TOKENS": "2000"
      }
    }
  }
}
```

`DOC_AGENT_HOME` matters here: without it the store is resolved from the server process's working directory, which the client sets and which is rarely the project you meant. Pass it explicitly. Run `doc-agent info` in the project to see the path to use.

## The retrieval contract

The store exists so an agent can answer questions without loading documents. The intended sequence:

```text
1. list_projects                 -> choose the project
2. search_documents              -> compact hits, each with estimated_tokens
3. read `snippet` / `text`       -> often already the answer
4. get_context([block_ids])      -> only for hits that need full text, budget-bounded
5. get_table_rows / list_visuals -> only when the question needs a whole table or a diagram

For a workbook, address it as a spreadsheet instead of hunting for blocks:

1. describe_workbook             -> how it calculates, defined names, sheet summary
2. list_sheets                   -> per sheet: rules, tables, extent, visibility
3. get_sheet_range(sheet, range) -> exactly those cells, paged
```

Steps 2 and 3 answer most questions. `search_documents` already returns the block's full `text` alongside a highlighted `snippet`, so a follow-up fetch is unnecessary unless the text was long enough to matter.

Every result reports `estimated_tokens`. Sum them before deciding what to retrieve, and prefer the smallest set that answers the question. When a hit sets `visual_required: true`, text alone cannot express the relationship — that block belongs to a diagram or spatial layout, and `list_visuals` identifies the corresponding image.

Cite answers with the `source` locator (`Sheet MOG · row 2`, `Page 3`, `Slide 2 · Title 1`) rather than the block ID, which is meaningless to a reader.

## Tool reference

| Tool | Parameters | Returns |
| --- | --- | --- |
| `list_projects` | — | `list[Project]` |
| `list_documents` | `project_id` | `list[DocumentSummary]` |
| `search_documents` | `project_id`, `query`, `limit=10` | `list[SearchResult]` |
| `get_block` | `block_id` | one `BlockRecord`, in full |
| `get_context` | `block_ids`, `max_tokens=None`, `mode="text"` | `list[BlockRecord]`, budget-bounded |
| `describe_workbook` | `document_id`, `version_id=None` | calculation mode, defined names, per-sheet summary |
| `list_sheets` | `document_id`, `version_id=None` | `list[SheetInfo]` with rules |
| `get_sheet_range` | `document_id`, `sheet`, `range=None`, `fields=None`, `cursor`, `limit` | one page of cells |
| `get_table_rows` | `document_id`, `cursor=None`, `limit=None` | one page of `table_row` blocks |
| `list_visuals` | `document_id` | `list[VisualRecord]` |
| `document_history` | `document_id` | `list[StoredVersion]`, oldest first |
| `diff_document_version` | `document_id`, `version_number` | `list[Change]` |

### search_documents

The primary entry point. `limit` defaults to **10** here — deliberately lower than the CLI's 20, because each result is spent from an agent's context — and is clamped to the range 1–100. Results are ordered best-match first.

```json
[
  {
    "block_id": "85144cdd-035c-56d1-84fa-b64e35025b01",
    "stable_key": "xlsx:a1285438168cb8b819a2:6b86b2",
    "document_id": "9557ae5f-ba26-41ef-a7c0-b6b2664723c4",
    "version_id": "a88f1f51-950a-4c88-9645-80c4b5b7511a",
    "logical_name": "fitgap.xlsx",
    "kind": "table_row",
    "text": "MOG-001\tCheckout\tPayPay\t12.5%",
    "snippet": "MOG-001\tCheckout\t[PayPay]\t12.5%",
    "source": {
      "kind": "xlsx",
      "sheet": "MOG",
      "row": 2,
      "cell": null,
      "cell_range": "A2:D2"
    },
    "score": -0.5029126622962939,
    "estimated_tokens": 8,
    "visual_required": false
  }
]
```

`score` is the raw FTS5 BM25 value, so it is **negative and lower is better**; results already arrive sorted, so treat it as a relative ranking signal only, never as a confidence percentage. Matches in `snippet` are wrapped in `[...]`, with ` … ` marking elided text.

Searching a project that does not exist raises an error rather than returning `[]`, so "no such project" is never mistaken for "no matches". An empty or whitespace-only query returns `[]` without error.

Paused documents are filtered out silently, which is the point of pausing. If a document you expect is missing from every result, check its `active` flag in `list_documents` before assuming the text is not there.

`search_documents` searches the whole project; it does not accept a `document_id` filter. To confine a question to one document, filter the results by `document_id`, or call `get_table_rows` for that document.

### get_block and get_context

`get_block` returns one block in full — values, formulas, and formatting — and spends no
budget: it is the precise path, for a block you have already chosen.

`get_context` is the bulk path. It takes several block IDs and returns as many as the
budget allows, where the budget governs **the whole serialized response**, not one field
of it. `mode` decides what the budget is spent on:

| `mode` | Each record carries | Use it for |
| --- | --- | --- |
| `text` (default) | identity, `source`, `text`, `visual_required` | reading content and citing it |
| `cells` | the above plus `payload` (raw values, formulas, cached values) and the in-version keys | checking values and formulas |
| `full` | the above plus `presentation` (number formats, merges, hidden columns) and the hashes | auditing how a value is displayed |

Every record reports what actually happened:

- `mode` — the shape it was rendered in, which may be **cheaper than the one asked for**.
  A block that will not fit as `full` is retried as `cells`, then `text`, because dropping
  cell detail loses less than cutting the content.
- `truncated` — the text itself had to be cut.
- `budget_exceeded` — present only when identity and source alone exceed the budget.
  Those cannot be dropped without breaking traceability, so a very small budget cannot be
  honoured; the overrun is declared rather than hidden. In practice a single spreadsheet
  row needs roughly 100 tokens before any content, so budget accordingly.

Later IDs are dropped rather than degraded, so one call returns one consistent shape;
ask again for the rest.

```json
{
  "block_id": "85144cdd-035c-56d1-84fa-b64e35025b01",
  "document_id": "9557ae5f-ba26-41ef-a7c0-b6b2664723c4",
  "version_id": "a88f1f51-950a-4c88-9645-80c4b5b7511a",
  "logical_name": "fitgap.xlsx",
  "kind": "table_row",
  "text": "MOG-001\tCheckout\tPayPay\t12.5%",
  "source": { "kind": "xlsx", "sheet": "MOG", "row": 2, "cell": null, "cell_range": "A2:D2" },
  "visual_required": false,
  "mode": "text",
  "truncated": false
}
```

In `cells` and `full`, `payload` and `presentation` appear as documented under
[Cell fidelity](#cell-fidelity).

### describe_workbook

Describes the workbook before any of its cells are read. For an audit this is the first
call, because one field in it changes how everything else should be read.

```json
{
  "document_id": "a02a580a-62d1-435d-96bd-0167f00a3993",
  "logical_name": "audit.xlsx",
  "version_id": "64505c7c-55a9-470a-b2e2-51e26edc5ef6",
  "is_current_version": true,
  "sheet_count": 2,
  "calculation": {
    "mode": "manual",
    "automatic": false,
    "full_calc_on_load": false,
    "iterative": false,
    "iterate_count": null
  },
  "defined_names": [
    { "name": "TaxRate", "refers_to": "MOG!$C$1", "scope": "workbook", "hidden": false }
  ],
  "sheets": [
    { "sheet": "MOG", "ordinal": 1, "hidden": false, "dimension": "A1:D4",
      "tables": 1, "validations": 2, "conditional_formats": 1 }
  ],
  "cached_value_warning": "This workbook calculates manually, so a cached formula result may never have been recalculated by its author. Treat every cached value as the last saved value, not a current one."
}
```

`calculation.automatic` is the finding to act on. A workbook set to `manual` may carry
formula results its own author never recalculated, so a `cached` value in it is stale by
design rather than by accident — and because that only matters in combination with
[Cell fidelity](#cell-fidelity)'s `value_state`, the warning is stated here rather than
left to be joined up from two calls.

`defined_names` are the names formulas use in place of addresses, at the scope that owns
them; sheet-scoped names appear on their sheet in `list_sheets`, not repeated here.

### list_sheets

Everything recorded per sheet: order, visibility, extent, defined tables, the input rules
the sheet enforces, its conditional-formatting conditions, and any sheet-scoped defined
names.

```json
[
  {
    "sheet": "MOG",
    "ordinal": 1,
    "kind": "worksheet",
    "state": "visible",
    "hidden": false,
    "dimension": "A1:D4",
    "tables": [{ "name": "FitGap", "ref": "A1:D4" }],
    "validations": [
      {
        "type": "list",
        "operator": null,
        "formula1": "\"Open,Closed,Blocked\"",
        "formula2": null,
        "ranges": ["B2:B100"],
        "allow_blank": false,
        "show_error_message": true,
        "error_title": "Invalid status",
        "error_message": "Pick from the list",
        "prompt_title": null,
        "prompt_message": null
      }
    ],
    "conditional_formats": [
      { "ranges": ["C2:C100"], "type": "cellIs", "operator": "lessThan",
        "formula": ["0"], "priority": 1, "stop_if_true": false }
    ],
    "defined_names": []
  }
]
```

`state` is what the file records — `visible`, `hidden`, or `veryHidden` — and `hidden` is
the plain reading of it. A hidden sheet is still extracted and still searchable; it is
reported so an audit can notice that content lives somewhere a reader would not look.

Rules are reported against the **ranges** they cover, not per cell: a rule governs a
range, and repeating it onto every cell would both bloat the response and lose the range.
A column restricted to a list is a different fact from a free-text column that happens to
hold the same word, and no cell value can tell them apart.

Conditional formatting is recorded as its condition, never as the appearance it produces:
the colour is not extracted, because what matters for review is the test and the range.

**`null` means unknown, `[]` means none.** A version extracted before these facts were
captured reports `null` for `validations`, `conditional_formats`, and `defined_names`, and
`describe_workbook` then carries `settings_available: false` with a note saying to
re-ingest the source. An empty list is a finding — the sheet has no such rules — and the
two are never conflated.

### get_sheet_range

Reads cells by address, which is how a spreadsheet is normally referenced. This is the
tool to use when the question is about particular cells: reading `MOG!F2:F4` costs about
190 estimated tokens, where the same answer via a whole-document read cost about 18,900.

`range` accepts A1 notation and defaults to the whole sheet:

```text
B2        one cell
B2:D10    a rectangle, corners in any order
B:D       whole columns
2:10      whole rows
MOG!B2    a sheet prefix, checked against the sheet argument
```

`fields` selects what each cell carries, defaulting to `display`, `raw_value`, `formula`,
`cached_value`. Available: `raw_value`, `formula`, `cached_value`, `data_type`, `display`,
`hyperlink`, `comment`, `number_format`, `merged_range`, `hidden_column`. `coordinate` is
always included, because a cell without its address cannot be cited or checked. An
unknown field name is refused and the available ones listed, rather than quietly ignored.

```json
{
  "document_id": "e7325dc8-f573-4a17-a9d3-039cb5d3c905",
  "logical_name": "big.xlsx",
  "version_id": "1aff3a6c-21ee-4722-9f10-591e4b3e85f2",
  "sheet": "MOG",
  "range": "F2:F3",
  "fields": ["formula"],
  "rows": [
    {
      "row": 2,
      "ordinal": 2,
      "block_id": "e4ae77f7-7f02-5b9e-a71c-deb07d24ae52",
      "cells": [{ "coordinate": "F2", "formula": "=D2*E2" }]
    }
  ],
  "next_cursor": null
}
```

`range` echoes the window actually read, so an open-ended request such as `B:D` comes
back with the concrete rectangle. A sheet name is matched case-insensitively; a name that
matches nothing names the sheets that do exist, because an empty page is indistinguishable
from a typo.

Empty cells are not stored, so a row returns only the cells that hold something: a gap in
the coordinates means the cell was empty in the source, not that it was dropped.

### get_table_rows

Returns a page of a document's `table_row` blocks in document order, each with the full
`payload`/`presentation` structure. Row 1 is typically the header row — it is returned as
data, not as a schema, so decide for yourself whether to treat the first row as labels.

```json
{ "rows": [ ... ], "next_cursor": "3:xlsx:a128...:6b86b2" }
```

Pass `next_cursor` back as `cursor` for the next page; `null` means that was the last one.
`limit` defaults to 50 and is capped at 500. The cursor is opaque — it pairs the ordinal
with the block's stable key, because `ordinal` counts rows **within a sheet** and a
workbook therefore repeats it once per sheet; paging on the ordinal alone skipped rows.
Do not construct one yourself: a cursor this API did not produce is refused.

`rows` is `[]` for a document with no current version. Use this for aggregate questions
("how many rows use PayPay?"), `get_sheet_range` when you know the address, and
`search_documents` when the question is about content.

### list_visuals

Metadata only, ordered by `stable_key`, for the current version. Each record carries `sha256`, `stored_path`, `media_type`, `width`, `height`, `alt_text`, `summary`, `decorative`, and `retrieval_enabled`. Returns `[]` when a document has no visuals.

Read the image from `stored_path` with your own file tooling when the question genuinely depends on the picture; skip anything marked `decorative`. No vision or OCR service is called on your behalf.

### document_history and diff_document_version

`document_history` lists versions oldest first, each with `version_id`, `version_number`, `source_sha256`, `created_at`, `media_type`, and `logical_name`.

```json
{
  "version_id": "a88f1f51-950a-4c88-9645-80c4b5b7511a",
  "document_id": "9557ae5f-ba26-41ef-a7c0-b6b2664723c4",
  "version_number": 1,
  "source_sha256": "10264a76b85a70fb…",
  "created_at": "2026-09-07T07:27:34.768168Z",
  "media_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  "logical_name": "fitgap.xlsx"
}
```

`diff_document_version` returns the changes that produced a given `version_number`. Each `Change` has a `kind` of `added`, `changed_semantic`, `changed_presentation`, `moved`, `deleted`, or `unchanged`, plus `stable_key`, `old_text`/`new_text`, and `old_source`/`new_source`.

The distinction that matters: `changed_semantic` means the content changed, while `changed_presentation` means only formatting did. When asked what actually changed between versions, filter to `changed_semantic`, `added`, and `deleted`. Blocks deleted in a later version remain in history but are absent from search and `get_block`.

## Reading one version

Every read defaults to the document's current version. Pass `version_id` to hold it to an
earlier one — `get_block`, `get_context`, `get_table_rows`, `get_sheet_range`,
`list_sheets`, and `list_visuals` all accept it, and `document_history` lists the ids.

Two calls either side of an ingest would otherwise answer from two different states with
nothing to say so. Three things prevent that:

- **Every response names the version it read.** `version_id` is what was actually read,
  not the document's current version, plus `is_current_version` so reading history is
  visible without comparing ids.
- **A cursor carries its version.** Continuing a paged read stays on the version the
  first page came from, even if the document is re-ingested midway. `is_current_version`
  then turns false on the later pages: the pages still describe one document, and you are
  told it is no longer the current one. Start again without a cursor to read the new
  version.
- **Contradictions are refused.** A cursor from one version plus a `version_id` for
  another raises rather than silently preferring one. A `version_id` belonging to a
  different document raises too.

A block id is derived from the document and the stable key, so a row keeps its id across
versions; naming a version is how the earlier copy is read.

## Cell fidelity

For a spreadsheet block, `payload` holds meaning and `presentation` holds appearance, as
two lists paired by position. This is where the fidelity rules become visible: the raw
value, the display string, and the number format stay separate, so an agent can reason on
`0.125` while quoting `12.5%`.

```json
{
  "payload": {
    "cells": [
      { "raw_value": "MOG-001", "display": "MOG-001", "data_type": "s",
        "formula": null, "cached_value": null, "comment": null, "hyperlink": null },
      { "raw_value": 0.125, "display": "12.5%", "data_type": "n",
        "formula": null, "cached_value": null, "comment": null, "hyperlink": null }
    ]
  },
  "presentation": {
    "cells": [
      { "coordinate": "A2", "number_format": "General", "merged_range": null, "hidden_column": false },
      { "coordinate": "D2", "number_format": "0.0%",    "merged_range": null, "hidden_column": false }
    ]
  }
}
```

Both of those are easy to over-read, so each cell also carries two states. They are
included by default in `get_sheet_range` and derived from the stored fields, so they
describe documents extracted before the states existed just as well as new ones.

`value_state` — where the value came from:

| State | Meaning |
| --- | --- |
| `literal` | The value is stored in the cell. Nothing was computed. |
| `cached` | A formula's last saved result. Real, but as old as the last save, and **no evidence of recalculation**. Report it as the last saved value, never as a computed figure. |
| `uncalculated` | The cell holds a formula and the file carries no result for it. Nothing was computed — which is not a result of zero, and not an empty cell. |

`display_state` — how far `display` can be trusted against what the sheet shows:

| State | Meaning |
| --- | --- |
| `exact` | Reproduced as the sheet shows it: plain and text formats, percentages, booleans, error text. |
| `normalized` | Deliberately canonical instead of the sheet's format: dates and times render ISO-8601, so `dd/mm/yyyy` comes back as `2026-03-01T00:00:00`. |
| `approximate` | The format carries rules that are **not applied** — thousands separators, currency, fixed decimals, scientific, custom. `#,##0.00` over `1234567.891` displays `1234567.891`, where the sheet shows `1,234,567.89`. Read `raw_value` with `number_format` and render it yourself. |
| `unavailable` | There is no value to display, because the formula was never calculated. The empty string means "not computed", not "empty". |

The two combine, and the combination is the point: a cell reading `value_state: cached`
with `display_state: approximate` is a figure that was neither recalculated here nor
rendered the way the sheet renders it. Neither fact is inferable from `display` alone.

Python evaluates no formulas, and no state claims otherwise.

Merged cells keep their value on the source top-left cell only; the other cells of the
range carry `merged_range` and no duplicated value.

## Field reference

### Source locators

`source.kind` selects the shape, so each format is cited in its own terms:

| `kind` | Fields |
| --- | --- |
| `xlsx` | `sheet`, `row`, `cell`, `cell_range` |
| `docx` | `section_path`, `paragraph_index`, `table_index`, `row_index`, `part` (`document`, header, or footer), `xml_id` |
| `pptx` | `slide_number`, `shape_id`, `shape_name`, `row_index` |
| `pdf` | `page_number`, `block_index`, `row_index`, `bbox` as `[x0, y0, x1, y1]` |

A DOCX page number is deliberately absent: it depends on rendering and is not stable identity.

### Block kinds

`heading`, `paragraph`, `list_item`, `table`, `table_row`, `cell`, `text_box`, `note`, `header`, `footer`, `chart`, `visual_reference`.

### Identity fields

`block_id` addresses a block for retrieval. `stable_key` is derived from content, not position, so it survives ordinary edits such as inserting a worksheet row and is what version comparison matches on — see [STABLE_IDENTITY.md](STABLE_IDENTITY.md). `container_key` points at the enclosing sheet, section, or slide. `semantic_hash` and `presentation_hash` are what separate a meaning change from a formatting change.

## Query syntax

`query` is passed to SQLite FTS5, so its operators work:

```text
PayPay                      single term
rollback OR ロールバック      alternatives, including CJK
"credit card"               phrase
refund*                     prefix
PayPay NOT refund           exclusion
NEAR(paypay refund, 5)      proximity
```

If a query is not valid FTS5 syntax, the server retries it once as a quoted phrase rather than failing; a failure with any other cause is raised as itself. This keeps punctuation-heavy strings such as `MOG-001 (v2)` safe, but it also means a malformed operator expression silently degrades to a literal search. When results look unexpectedly narrow, check the query's syntax first.

Matching is per block. Terms spread across different rows or paragraphs will not match a single block, so search the distinctive term and inspect neighbours by `ordinal` rather than combining every keyword into one query.

## Token budget and truncation

`get_context` applies the budget from `DOC_AGENT_MAX_CONTEXT_TOKENS` (default 2000) unless `max_tokens` is passed explicitly. Its policy:

- Blocks are added in the order given, while the accumulated text stays within budget.
- The first block that would exceed the budget stops the walk; later IDs are not returned. Pass IDs in priority order.
- If the very first block alone exceeds the budget, a trimmed prefix of it is returned with `truncated: true` rather than nothing.
- `max_tokens` of `0` or less returns `[]`.

So a short result list is a budget signal, not an error: compare the number of records returned against the number of IDs requested, and check `truncated` before treating any text as complete. Token counts are estimates for budgeting, not a tokenizer's exact output.

## Errors

Failures come back as MCP tool errors (`isError: true`) with a plain message, not as empty results:

```text
Error executing tool get_block: Block not found: nope
Error executing tool search_documents: Project not found: bad-project
```

The distinction to preserve when reporting back: `Project not found` and `Block not found` mean the identifier is wrong, while an empty list means the identifier was valid and nothing matched. Do not retry a not-found error with the same identifier; re-resolve it with `list_projects` or `list_documents`.

## Anti-patterns

| Avoid | Instead |
| --- | --- |
| Calling `get_table_rows` to explore a document | `search_documents` first; load the full table only for aggregate questions. |
| Fetching every search hit with `get_context` | Read `snippet` and `text` from the results; fetch only what is still missing. |
| Requesting a huge `max_tokens` to avoid truncation | Retrieve fewer, better-targeted blocks; the budget is the point of the store. |
| Treating `score` as a confidence value | Use it only as relative ranking; results are pre-sorted. |
| Quoting `cached_value` as a computed figure | State it as the value last saved by the source application. |
| Citing `block_id` in an answer | Cite the `source` locator, which a reader can open. |
| Reconstructing a document by paging through blocks | Read the source file directly, or export the package with `doc-agent export`. |
