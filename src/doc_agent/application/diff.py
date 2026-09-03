"""Compare normalized block versions without knowing their source file format."""

from __future__ import annotations

from doc_agent.domain.hashing import hash_presentation, hash_semantic
from doc_agent.domain.models import Block, Change, DiffResult


class VersionDiffer:
    """Classify stable-key changes into semantic, presentation, move, add, or delete."""

    def compare(self, old: list[Block], new: list[Block]) -> DiffResult:
        old_map = {block.stable_key: block for block in old}
        new_map = {block.stable_key: block for block in new}
        changes: list[Change] = []
        for key in sorted(old_map.keys() | new_map.keys()):
            previous = old_map.get(key)
            current = new_map.get(key)
            if previous is None and current is not None:
                changes.append(self._change("added", key, None, current))
                continue
            if current is None and previous is not None:
                changes.append(self._change("deleted", key, previous, None))
                continue
            assert previous is not None and current is not None
            if hash_semantic(previous) != hash_semantic(current):
                kind = "changed_semantic"
            elif self._structural_source(previous) != self._structural_source(current):
                kind = "moved"
            elif hash_presentation(previous) != hash_presentation(current):
                kind = "changed_presentation"
            else:
                kind = "unchanged"
            changes.append(self._change(kind, key, previous, current))
        return DiffResult(changes=changes)

    @staticmethod
    def _structural_source(block: Block) -> tuple:
        source = block.source.model_dump(mode="json")
        for field in ("row", "cell", "cell_range", "paragraph_index", "table_index", "row_index", "slide_number"):
            source.pop(field, None)
        return tuple(sorted((key, str(value)) for key, value in source.items())) + (block.ordinal,)

    @staticmethod
    def _change(kind: str, key: str, old: Block | None, new: Block | None) -> Change:
        return Change(
            kind=kind,
            stable_key=key,
            old_text=old.text if old else None,
            new_text=new.text if new else None,
            old_source=old.source.model_dump(mode="json") if old else None,
            new_source=new.source.model_dump(mode="json") if new else None,
        )
