"""Dependency-free token estimation suitable for retrieval budgeting."""

from __future__ import annotations

import math
import re

_CJK = re.compile(r"[\u3040-\u30ff\u3400-\u9fff]")


class HeuristicTokenEstimator:
    """Estimate tokens conservatively for mixed Japanese/Vietnamese/English text."""

    def estimate(self, text: str) -> int:
        if not text:
            return 0
        cjk = len(_CJK.findall(text))
        other = max(0, len(text) - cjk)
        return max(1, cjk + math.ceil(other / 4))
