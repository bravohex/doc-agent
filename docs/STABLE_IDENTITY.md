# Stable identity across document versions

Doc Agent separates **source position** from **semantic identity** so ordinary edits such as inserting a worksheet row do not make every later block appear new.

## XLSX

A worksheet row uses the first meaningful source value as its primary identity. Physical coordinates such as `A17` or row `17` remain in the source locator for traceability, but they are deliberately excluded from the stable key.

If the same primary value occurs more than once in a sheet, Doc Agent adds a deterministic occurrence number. Identical duplicate rows cannot be matched perfectly without a durable business identifier in the source, so this limitation is explicit rather than hidden.

This means a row such as:

```text
REQ-001    Voucher    A
```

keeps its block identity when it moves from row 10 to row 11 because another row was inserted above it. The source locator changes, allowing version diffing to classify the change as a move rather than an add/delete pair.

## DOCX and PPTX

DOCX stable keys use structural heading context plus content identity. PPTX keys use slide context plus source shape identity/content. Rendered page numbers are not treated as stable DOCX identity because pagination is renderer-dependent.

Repeated content resolves the same way it does in XLSX. Two identical paragraphs under one heading, two table rows sharing a first cell, or two slides carrying the same title (a PPTX shape id is only unique within its slide) all yield one identity seed, so later occurrences receive a deterministic occurrence suffix in document order. The first occurrence keeps the unsuffixed key, which leaves identities that were never ambiguous unchanged across versions.

## PDF

A PDF has no structural identity to borrow, so a block is identified by its text alone. Page number and bounding box stay in the source locator, which means text that reflows onto a later page keeps its identity and diffs as a move. Repeated text is disambiguated by occurrence, as everywhere else.

## Source of truth

Stable keys are retrieval/versioning identifiers only. They never replace the original source locator, raw values, formulas, or visual metadata. The current source position remains available for traceability in every stored block.
