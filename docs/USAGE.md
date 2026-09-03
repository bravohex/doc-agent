# Usage patterns

## Retrieval-first agent workflow

Recommended agent behavior:

1. Identify the project.
2. Search by exact ID or keywords.
3. Inspect compact search results and token estimates.
4. Fetch only the needed blocks/table rows.
5. Fetch visual metadata only when text cannot answer the relationship/layout question.
6. Preserve source locators when citing an answer internally.

## When to inspect a visual

Text is usually enough for:

- exact values
- requirement IDs
- table filtering/counting
- paragraphs and notes

Open the corresponding visual when the question depends on:

- arrows
- spatial grouping
- architecture relationships
- chart appearance not represented by extracted series
- screenshot content

## Version questions

For “what changed?” queries, use version history and stored changes instead of comparing two full Office files in agent context.
