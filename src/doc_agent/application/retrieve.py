"""Source-backed block and context retrieval use cases."""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Literal

from doc_agent.ports.repositories import DocumentRepository, Record
from doc_agent.ports.tokens import TokenEstimator

type ContextMode = Literal["text", "cells", "full"]

#: Cheapest first. A block that will not fit in the requested shape is retried in the
#: cheaper ones before its text is cut, because dropping cell detail loses less than
#: truncating the content itself.
_MODES: tuple[ContextMode, ...] = ("text", "cells", "full")

#: Enough to read the content, cite it, and fetch it again. The internal keys are left
#: out because UUIDs cost more than the text of a spreadsheet row: measured on a
#: four-column row, identity fields were 55 estimated tokens against 11 for the values.
_TEXT_FIELDS = (
    "block_id",
    "document_id",
    "version_id",
    "logical_name",
    "kind",
    "text",
    "source",
    "visual_required",
)

#: The keys that address a block inside its version, wanted once cell detail is.
_CELL_FIELDS = ("stable_key", "container_key", "ordinal", "payload")

_FULL_FIELDS = ("presentation", "semantic_hash", "presentation_hash")


def project(record: Record, mode: ContextMode) -> Record:
    """Reduce a block record to the fields a mode promises.

    ``text`` answers "what does it say", ``cells`` adds the values behind it, and
    ``full`` adds the formatting layer. The budget is spent on what the caller asked
    for rather than on detail it did not.
    """

    keys = _TEXT_FIELDS
    if mode in ("cells", "full"):
        keys += _CELL_FIELDS
    if mode == "full":
        keys += _FULL_FIELDS
    return {key: record[key] for key in keys if key in record}


def response_cost(records: Sequence[Record], *, estimator: TokenEstimator) -> int:
    """Estimate what returning these records actually costs.

    Records leave as JSON, so the whole serialized response is measured. Counting only
    ``text`` was the earlier mistake: a budget of ten tokens still returned every cell
    and its formatting.
    """

    return estimator.estimate(json.dumps(records, ensure_ascii=False, default=str))


def trim_to_budget(
    texts: Sequence[str], *, estimator: TokenEstimator, max_tokens: int
) -> list[str]:
    """Select text without ever exceeding the configured context budget.

    If the first relevant block alone exceeds the budget, keep a bounded prefix rather
    than returning no context at all. This is intentionally a retrieval rendering
    operation; the stored source block remains unchanged.
    """

    if max_tokens <= 0:
        return []
    selected: list[str] = []
    for text in texts:
        candidate = "\n".join([*selected, text])
        if estimator.estimate(candidate) <= max_tokens:
            selected.append(text)
            continue
        if selected:
            break
        low, high = 0, len(text)
        while low < high:
            middle = (low + high + 1) // 2
            if estimator.estimate(text[:middle]) <= max_tokens:
                low = middle
            else:
                high = middle - 1
        if low:
            selected.append(text[:low])
        break
    return selected


class RetrieveContent:
    """Retrieve exact blocks while applying an injected token budget policy to context."""

    def __init__(
        self,
        repository: DocumentRepository,
        tokens: TokenEstimator,
        *,
        max_tokens: int = 2_000,
    ) -> None:
        self.repository = repository
        self.tokens = tokens
        self.max_tokens = max_tokens

    def block(self, block_id: str, *, mode: ContextMode = "full") -> Record:
        """Return one block. Unbudgeted and full by default: this is the precise path."""

        return project(self.repository.get_block(block_id), mode)

    def context(
        self,
        block_ids: list[str],
        *,
        max_tokens: int | None = None,
        mode: ContextMode = "text",
    ) -> list[Record]:
        """Return blocks whose whole serialized response stays inside the budget.

        Each record reports the ``mode`` it was actually rendered in and whether its
        text had to be cut, so a caller can tell a complete answer from a bounded one.
        """

        max_tokens = self.max_tokens if max_tokens is None else max_tokens
        if max_tokens <= 0:
            return []
        selected: list[Record] = []
        for block_id in block_ids:
            record = self.repository.get_block(block_id)
            candidate = {**project(record, mode), "mode": mode, "truncated": False}
            if response_cost([*selected, candidate], estimator=self.tokens) <= max_tokens:
                selected.append(candidate)
                continue
            if selected:
                # Later ids are dropped rather than degraded, so one budget produces one
                # consistent shape; the caller asks again for the rest.
                break
            selected.append(self._fit_one(record, mode=mode, max_tokens=max_tokens))
            break
        return selected

    def _fit_one(self, record: Record, *, mode: ContextMode, max_tokens: int) -> Record:
        """Fit a single oversized block, giving up detail before giving up content."""

        cheaper: list[ContextMode] = [m for m in _MODES if _MODES.index(m) < _MODES.index(mode)]
        for fallback in reversed(cheaper):
            candidate = {**project(record, fallback), "mode": fallback, "truncated": False}
            if response_cost([candidate], estimator=self.tokens) <= max_tokens:
                return candidate

        # Even the text alone is too big, so bound it and say so.
        bare = {**project(record, "text"), "mode": "text", "truncated": True}
        text = str(record.get("text", ""))
        overhead = response_cost([{**bare, "text": ""}], estimator=self.tokens)
        trimmed = trim_to_budget(
            [text], estimator=self.tokens, max_tokens=max(0, max_tokens - overhead)
        )
        bare["text"] = trimmed[0] if trimmed else ""
        if response_cost([bare], estimator=self.tokens) > max_tokens:
            # Identity and source cannot be dropped without breaking traceability, so a
            # budget below that floor cannot be met. Returning nothing would be useless
            # and pretending it fit would be a lie, so the overrun is declared.
            bare["budget_exceeded"] = True
        return bare
