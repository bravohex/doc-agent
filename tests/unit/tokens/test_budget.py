from __future__ import annotations

from doc_agent.adapters.tokens.heuristic import HeuristicTokenEstimator
from doc_agent.application.retrieve import RetrieveContent, trim_to_budget


def test_context_trimming_never_exceeds_budget() -> None:
    estimator = HeuristicTokenEstimator()
    texts = ["alpha " * 50, "beta " * 50, "gamma " * 50]
    selected = trim_to_budget(texts, estimator=estimator, max_tokens=60)
    assert selected
    assert estimator.estimate("\n".join(selected)) <= 60


class SingleBlockRepository:
    def __init__(self, text: str) -> None:
        self.text = text

    def get_block(self, block_id: str, *, version_id: str | None = None) -> dict[str, object]:
        return {"block_id": block_id, "text": self.text}


def test_an_oversized_first_block_yields_flagged_context_rather_than_nothing() -> None:
    estimator = HeuristicTokenEstimator()
    retrieve = RetrieveContent(SingleBlockRepository("alpha " * 200), estimator)  # type: ignore[arg-type]

    selected = retrieve.context(["block-1"], max_tokens=20)

    assert len(selected) == 1
    assert selected[0]["truncated"] is True
    assert estimator.estimate(str(selected[0]["text"])) <= 20
    assert str(selected[0]["text"]) in "alpha " * 200


def test_blocks_inside_the_budget_are_returned_whole() -> None:
    retrieve = RetrieveContent(SingleBlockRepository("alpha"), HeuristicTokenEstimator())  # type: ignore[arg-type]

    selected = retrieve.context(["block-1"], max_tokens=100)

    assert selected[0]["text"] == "alpha"
    assert selected[0]["truncated"] is False
