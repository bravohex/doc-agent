from __future__ import annotations

from doc_agent.adapters.visuals.null_analyzer import NullVisualAnalyzer


def test_null_visual_analyzer_never_invents_content() -> None:
    analyzer = NullVisualAnalyzer()
    assert analyzer.summarize(b"binary", media_type="image/png") is None
    assert (
        analyzer.summarize(b"binary", media_type="image/png", nearby_text="Architecture")
        == "Architecture"
    )
