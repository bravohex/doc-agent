from __future__ import annotations

from doc_agent.application.diff import VersionDiffer
from doc_agent.domain.models import Block, BlockKind, XlsxLocator


def block(text: str, presentation: str = "a", ordinal: int = 2) -> Block:
    return Block(
        stable_key="mog-001",
        kind=BlockKind.TABLE_ROW,
        ordinal=ordinal,
        text=text,
        source=XlsxLocator(sheet="MOG", row=ordinal, cell_range=f"A{ordinal}:C{ordinal}"),
        payload={"id": "MOG-001"},
        presentation={"fill": presentation},
    )


def test_diff_classifies_semantic_presentation_move_add_delete() -> None:
    differ = VersionDiffer()
    assert differ.compare([block("A")], [block("B")]).changes[0].kind == "changed_semantic"
    assert differ.compare([block("A")], [block("A", "b")]).changes[0].kind == "changed_presentation"
    assert (
        differ.compare([block("A", ordinal=2)], [block("A", ordinal=8)]).changes[0].kind == "moved"
    )
    assert differ.compare([], [block("A")]).changes[0].kind == "added"
    assert differ.compare([block("A")], []).changes[0].kind == "deleted"
