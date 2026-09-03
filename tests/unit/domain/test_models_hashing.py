from __future__ import annotations

from doc_agent.domain.hashing import hash_presentation, hash_semantic
from doc_agent.domain.identifiers import stable_key
from doc_agent.domain.models import Block, BlockKind, XlsxLocator


def test_semantic_and_presentation_hashes_change_independently() -> None:
    locator = XlsxLocator(sheet="MOG", row=5, cell_range="A5:C5")
    block = Block(
        stable_key="mog-1",
        kind=BlockKind.TABLE_ROW,
        ordinal=5,
        text="MOG-001\tPayPay\tA",
        source=locator,
        payload={"cells": ["MOG-001", "PayPay", "A"]},
        presentation={"fill": "red"},
    )
    sem1 = hash_semantic(block)
    pre1 = hash_presentation(block)
    changed_style = block.model_copy(update={"presentation": {"fill": "blue"}})
    assert hash_semantic(changed_style) == sem1
    assert hash_presentation(changed_style) != pre1
    changed_text = block.model_copy(update={"text": "MOG-001\tPayPay\tC"})
    assert hash_semantic(changed_text) != sem1


def test_stable_key_is_deterministic_and_not_ordinal_only() -> None:
    a = stable_key("xlsx", "MOG", "MOG-001", hint="PayPay")
    b = stable_key("xlsx", "MOG", "MOG-001", hint="PayPay")
    c = stable_key("xlsx", "MOG", "MOG-002", hint="PayPay")
    assert a == b
    assert a != c
    assert "5" not in stable_key("xlsx", "MOG", "identity", hint="5")
