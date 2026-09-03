from __future__ import annotations

from pathlib import Path

from doc_agent.adapters.filesystem.visual_store import FileVisualStore


def test_visual_store_deduplicates_by_content_hash(tmp_path: Path) -> None:
    store = FileVisualStore(tmp_path)
    first = store.put(b"same", media_type="image/png")
    second = store.put(b"same", media_type="image/png")
    assert first.sha256 == second.sha256
    assert first.path == second.path
    assert first.path.exists()
