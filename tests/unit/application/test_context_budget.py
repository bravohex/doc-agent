"""The context budget has to govern the response, not one field of it.

Measuring only ``text`` meant a budget of ten tokens still returned every cell and its
formatting: the response was larger than the number asked for, and said it was not
truncated. These tests pin the response size itself.
"""

from __future__ import annotations

import json

import pytest

from doc_agent.adapters.tokens.heuristic import HeuristicTokenEstimator
from doc_agent.application.retrieve import RetrieveContent, project, response_cost
from doc_agent.ports.repositories import Record

ESTIMATOR = HeuristicTokenEstimator()


def _block(block_id: str, text: str, columns: int = 4) -> Record:
    """A block shaped like a spreadsheet row, whose detail dwarfs its text."""

    return {
        "block_id": block_id,
        "document_id": "doc-0000-0000-0000-000000000001",
        "version_id": "ver-0000-0000-0000-000000000001",
        "stable_key": f"xlsx:{block_id}:key",
        "container_key": "xlsx:sheet:key",
        "logical_name": "fitgap.xlsx",
        "kind": "table_row",
        "ordinal": 2,
        "text": text,
        "source": {"kind": "xlsx", "sheet": "MOG", "row": 2, "cell_range": "A2:D2"},
        "visual_required": False,
        "semantic_hash": "a" * 64,
        "presentation_hash": "b" * 64,
        "payload": {
            "cells": [
                {
                    "raw_value": f"value-{index}",
                    "display": f"value-{index}",
                    "formula": None,
                    "cached_value": None,
                    "data_type": "s",
                    "hyperlink": None,
                    "comment": None,
                }
                for index in range(columns)
            ]
        },
        "presentation": {
            "cells": [
                {
                    "coordinate": f"A{index}",
                    "number_format": "General",
                    "merged_range": None,
                    "hidden_column": False,
                }
                for index in range(columns)
            ]
        },
    }


class _Repository:
    def __init__(self, *blocks: Record) -> None:
        self.blocks = {str(block["block_id"]): block for block in blocks}

    def get_block(self, block_id: str) -> Record:
        return self.blocks[block_id]


def _retrieve(*blocks: Record, max_tokens: int = 2_000) -> RetrieveContent:
    return RetrieveContent(_Repository(*blocks), ESTIMATOR, max_tokens=max_tokens)  # type: ignore[arg-type]


def _cost(records: list[Record]) -> int:
    return response_cost(records, estimator=ESTIMATOR)


@pytest.mark.parametrize("mode", ["text", "cells", "full"])
def test_the_response_stays_within_the_budget_whenever_that_is_possible(mode: str) -> None:
    block = _block("b1", "MOG-001\tCheckout\tPayPay", columns=12)
    retrieve = _retrieve(block)

    # 400 tokens comfortably clears the identity floor for one block.
    records = retrieve.context(["b1"], max_tokens=400, mode=mode)  # type: ignore[arg-type]

    assert _cost(records) <= 400


def test_a_wide_row_no_longer_returns_its_cells_under_a_tiny_budget() -> None:
    """The reported bug: max_tokens=10 still returned the whole payload."""

    block = _block("b1", "short", columns=40)
    retrieve = _retrieve(block)

    records = retrieve.context(["b1"], max_tokens=10, mode="full")

    assert "payload" not in records[0]
    assert "presentation" not in records[0]
    assert records[0]["mode"] == "text"
    # The floor cannot be met, and that is stated rather than implied.
    assert records[0]["truncated"] is True
    assert records[0]["budget_exceeded"] is True


def test_a_budget_that_cannot_be_met_is_declared_not_hidden() -> None:
    block = _block("b1", "short", columns=4)

    generous = _retrieve(block).context(["b1"], max_tokens=2_000, mode="text")
    assert "budget_exceeded" not in generous[0]
    assert generous[0]["truncated"] is False

    starved = _retrieve(block).context(["b1"], max_tokens=5, mode="text")
    assert starved[0]["budget_exceeded"] is True


def test_detail_is_given_up_before_content_is() -> None:
    """A block that will not fit as `full` is retried cheaper before its text is cut."""

    block = _block("b1", "MOG-001\tCheckout\tPayPay\t12.5%", columns=8)
    retrieve = _retrieve(block)

    full_cost = _cost([{**project(block, "full"), "mode": "full", "truncated": False}])
    cells_cost = _cost([{**project(block, "cells"), "mode": "cells", "truncated": False}])
    assert cells_cost < full_cost, "the fixture does not exercise degradation"

    records = retrieve.context(["b1"], max_tokens=cells_cost, mode="full")

    assert records[0]["mode"] == "cells"
    assert records[0]["truncated"] is False
    assert records[0]["text"] == block["text"], "text was cut before detail was dropped"


def test_later_blocks_are_dropped_rather_than_overflowing_the_budget() -> None:
    first = _block("b1", "first row of the sheet", columns=6)
    second = _block("b2", "second row of the sheet", columns=6)
    retrieve = _retrieve(first, second)

    one = retrieve.context(["b1"], max_tokens=2_000, mode="cells")
    budget = _cost(one) + 5

    records = retrieve.context(["b1", "b2"], max_tokens=budget, mode="cells")

    assert [record["block_id"] for record in records] == ["b1"]
    assert _cost(records) <= budget


def test_block_stays_full_and_unbudgeted() -> None:
    """`get_block` is the precise path; only `get_context` spends a budget."""

    block = _block("b1", "MOG-001", columns=6)

    record = _retrieve(block).block("b1")

    assert record["payload"] == block["payload"]
    assert record["presentation"] == block["presentation"]


def test_response_cost_counts_the_whole_serialized_response() -> None:
    block = _block("b1", "short", columns=20)
    records = [{**project(block, "full"), "mode": "full", "truncated": False}]

    assert _cost(records) == ESTIMATOR.estimate(
        json.dumps(records, ensure_ascii=False, default=str)
    )
    # Counting only the text is what made the budget meaningless.
    assert _cost(records) > ESTIMATOR.estimate(str(block["text"])) * 5
