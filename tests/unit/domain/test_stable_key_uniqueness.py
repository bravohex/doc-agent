from __future__ import annotations

from doc_agent.domain.identifiers import unique_stable_keys
from doc_agent.domain.models import Block, BlockKind, ExtractedDocument, XlsxLocator


def _block(key: str, ordinal: int) -> Block:
    return Block(
        stable_key=key,
        kind=BlockKind.PARAGRAPH,
        ordinal=ordinal,
        text=f"text {ordinal}",
        source=XlsxLocator(sheet="S1", row=ordinal),
    )


def test_first_occurrence_keeps_its_key_and_repeats_are_disambiguated() -> None:
    assert unique_stable_keys(["a", "b", "a", "a", "b"]) == ["a", "b", "a#2", "a#3", "b#2"]


def test_disambiguation_never_collides_with_an_existing_suffixed_key() -> None:
    assert len(set(unique_stable_keys(["a", "a#2", "a", "a"]))) == 4


def test_extracted_document_enforces_unique_block_keys() -> None:
    document = ExtractedDocument(
        logical_name="dup.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        blocks=[_block("docx:aaa:bbb", 1), _block("docx:aaa:bbb", 2)],
    )
    keys = [block.stable_key for block in document.blocks]
    assert keys[0] == "docx:aaa:bbb"
    assert len(set(keys)) == 2
