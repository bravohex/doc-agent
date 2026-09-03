from __future__ import annotations

from doc_agent.adapters.tokens.heuristic import HeuristicTokenEstimator, trim_to_budget


def test_context_trimming_never_exceeds_budget() -> None:
    estimator = HeuristicTokenEstimator()
    texts = ["alpha " * 50, "beta " * 50, "gamma " * 50]
    selected = trim_to_budget(texts, estimator=estimator, max_tokens=60)
    assert selected
    assert estimator.estimate("\n".join(selected)) <= 60
