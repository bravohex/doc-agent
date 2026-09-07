# MCP server reference

Doc Agent exposes its knowledge store to agents through a read-oriented MCP server over stdio. This document is the contract: what each tool accepts, what it returns, and how to query the store without defeating its purpose.

- [Guarantees](#guarantees)
- [Registration](#registration)
- [The retrieval contract](#the-retrieval-contract)
- [Tool reference](#tool-reference)
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
| Current version by default | `get_block`, `get_context`, `get_table_rows`, and `list_visuals` resolve against each document's **current** version. Earlier versions are reachable only through `document_history` and `diff_document_version`. |
| Source-traceable | Every block and search result carries a `source` locator expressed in its own format's terms. |
| Bounded context | `get_context` never exceeds the configured token budget. |

## Registration

There are two transports. Both expose exactly the same nine tools.

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
| `get_block` | `block_id` | `BlockRecord` |
| `get_context` | `block_ids`, `max_tokens=None` | `list[BlockRecord]` with `truncated` |
| `get_table_rows` | `document_id` | `list[BlockRecord]` of `kind: table_row` |
| `list_visuals` | `document_id` | `list[VisualRecord]` |
| `document_history` | `document_id` | `list[StoredVersion]`, oldest first |
| `diff_document_version` | `document_id`, `version_number` | `list[Change]` |

### search_documents

The primary entry point. `limit` defaults to **10** here (the CLI's `search` defaults to 20) and is clamped to the range 1–100. Results are ordered best-match first.

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

`search_documents` searches the whole project; it does not accept a `document_id` filter. To confine a question to one document, filter the results by `document_id`, or call `get_table_rows` for that document.

### get_block and get_context

`get_block` returns one whole block. `get_context` takes several block IDs and returns as many whole blocks as the budget allows — see [Token budget and truncation](#token-budget-and-truncation). Prefer `get_context` even for a single ID, because it enforces the budget and reports truncation.

A block record carries the text, its source locator, and two format-specific dictionaries:

```json
{
  "block_id": "85144cdd-035c-56d1-84fa-b64e35025b01",
  "document_id": "9557ae5f-ba26-41ef-a7c0-b6b2664723c4",
  "version_id": "a88f1f51-950a-4c88-9645-80c4b5b7511a",
  "stable_key": "xlsx:a1285438168cb8b819a2:6b86b2",
  "container_key": "xlsx:ac16037e0426f272594c:e3b0c4",
  "kind": "table_row",
  "ordinal": 2,
  "text": "MOG-001\tCheckout\tPayPay\t12.5%",
  "semantic_hash": "ef4494fa330d46be…",
  "presentation_hash": "e75eff358e399b71…",
  "visual_required": 0,
  "logical_name": "fitgap.xlsx",
  "source": { "kind": "xlsx", "sheet": "MOG", "row": 2, "cell": null, "cell_range": "A2:D2" },
  "payload": { "cells": [ … ] },
  "presentation": { "cells": [ … ] },
  "truncated": false
}
```

`payload` holds meaning; `presentation` holds appearance. For XLSX, this is where the fidelity rules become visible — the raw value, the display string, and the number format stay separate, so an agent can reason on `0.125` while quoting `12.5%`:

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

For a formula cell, `formula` holds the expression and `cached_value` the value stored by the application that last saved the file. Python does not evaluate formulas, so `cached_value` may be absent or stale — never present it as a computed result.

Note that `visual_required` arrives as `0`/`1` in block records but as `false`/`true` in search results. Coerce it rather than comparing identity.

### get_table_rows

Returns every `table_row` block of a document's current version, ordered by `ordinal`, each with the same `payload`/`presentation` structure as above. Row 1 is typically the header row — it is returned as data, not as a schema, so decide for yourself whether to treat the first row as labels.

Returns `[]` for a document with no current version. This tool loads a whole table; use it when the question is aggregate ("how many rows use PayPay?") and `search_documents` when the question is specific.

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

If a query is not valid FTS5 syntax, the server automatically retries it as a quoted phrase rather than failing. This keeps punctuation-heavy strings such as `MOG-001 (v2)` safe, but it also means a malformed operator expression silently degrades to a literal search. When results look unexpectedly narrow, check the query's syntax first.

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
