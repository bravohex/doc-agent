"""Token estimation port."""

from __future__ import annotations

from typing import Protocol


class TokenEstimator(Protocol):
    """Estimate prompt-token cost without binding the core to a tokenizer vendor."""

    def estimate(self, text: str) -> int: ...
