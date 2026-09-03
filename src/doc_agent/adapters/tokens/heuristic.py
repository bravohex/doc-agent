"""Dependency-free token estimation suitable for retrieval budgeting."""

from __future__ import annotations

import math
import re
from collections.abc import Sequence

from doc_agent.ports.tokens import TokenEstimator


_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")


class HeuristicTokenEstimator:
    """Estimate tokens conservatively for mixed Japanese/Vietnamese/English text."""

    def estimate(self, text: str) -> int:
        if not text:
            return 0
        cjk = len(_CJK.findall(text))
        other = max(0, len(text) - cjk)
        return max(1, cjk + math.ceil(other / 4))


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
