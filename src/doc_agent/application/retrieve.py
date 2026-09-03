"""Source-backed block and context retrieval use cases."""

from __future__ import annotations

from doc_agent.ports.repositories import DocumentRepository
from doc_agent.ports.tokens import TokenEstimator


class RetrieveContent:
    """Retrieve exact blocks while applying an injected token budget policy to context."""

    def __init__(self, repository: DocumentRepository, tokens: TokenEstimator) -> None:
        self.repository = repository
        self.tokens = tokens

    def block(self, block_id: str) -> dict:
        return self.repository.get_block(block_id)

    def context(self, block_ids: list[str], *, max_tokens: int = 2_000) -> list[dict]:
        if max_tokens <= 0:
            return []
        selected: list[dict] = []
        running_text = ""
        for block_id in block_ids:
            block = self.repository.get_block(block_id)
            text = str(block["text"])
            candidate = f"{running_text}\n{text}" if running_text else text
            if self.tokens.estimate(candidate) > max_tokens:
                break
            selected.append(block)
            running_text = candidate
        return selected
