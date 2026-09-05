"""Source-backed block and context retrieval use cases."""

from __future__ import annotations

from collections.abc import Sequence

from doc_agent.ports.repositories import DocumentRepository, Record
from doc_agent.ports.tokens import TokenEstimator


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

    def block(self, block_id: str) -> Record:
        return self.repository.get_block(block_id)

    def context(self, block_ids: list[str], *, max_tokens: int | None = None) -> list[Record]:
        """Return whole blocks within the budget, flagging any text that had to be cut."""

        max_tokens = self.max_tokens if max_tokens is None else max_tokens
        if max_tokens <= 0:
            return []
        selected: list[Record] = []
        running_text = ""
        for block_id in block_ids:
            block = self.repository.get_block(block_id)
            text = str(block["text"])
            candidate = f"{running_text}\n{text}" if running_text else text
            if self.tokens.estimate(candidate) <= max_tokens:
                selected.append({**block, "truncated": False})
                running_text = candidate
                continue
            if selected:
                break
            # A single oversized block must still yield context rather than nothing.
            trimmed = trim_to_budget([text], estimator=self.tokens, max_tokens=max_tokens)
            if trimmed:
                selected.append({**block, "text": trimmed[0], "truncated": True})
            break
        return selected
