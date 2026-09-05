from __future__ import annotations

import io
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pypdf
import pytest
from PIL import Image

from doc_agent.adapters.extractors.pdf import PdfExtractor, PdfLimits
from doc_agent.domain.errors import EncryptedDocumentError, UnsafePackageError
from doc_agent.domain.models import BlockKind

# A ruled two-column table: three horizontal rules and three vertical ones.
TABLE_RULES = [
    (60, 730, 400, 730),
    (60, 710, 400, 710),
    (60, 690, 400, 690),
    (60, 690, 60, 730),
    (190, 690, 190, 730),
    (400, 690, 400, 730),
]

REPORT_PAGES: list[dict[str, Any]] = [
    {
        "lines": [
            (72, 720, 16, "Fit Gap Report"),
            (72, 690, 11, "PayPay settlement is in scope for the first"),
            (72, 676, 11, "release and is rehearsed twice."),
            (72, 600, 11, "Rollback stays a separate decision."),
        ]
    },
    {
        "lines": [
            (72, 720, 11, "ID"),
            (200, 720, 11, "System"),
            (72, 700, 11, "IF-01"),
            (200, 700, 11, "KUROSHIO"),
        ],
        "rules": TABLE_RULES,
    },
    {"lines": []},
]


def _pdf(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path


def test_wrapped_lines_become_one_paragraph_and_a_gap_starts_another(
    tmp_path: Path, write_pdf: Callable[[Sequence[dict[str, Any]]], bytes]
) -> None:
    source = _pdf(tmp_path / "report.pdf", write_pdf(REPORT_PAGES))

    extracted = PdfExtractor().extract(source)

    paragraphs = [b for b in extracted.blocks if b.kind == BlockKind.PARAGRAPH]
    texts = [b.text for b in paragraphs]
    assert "Fit Gap Report" in texts
    assert "PayPay settlement is in scope for the first release and is rehearsed twice." in texts
    assert "Rollback stays a separate decision." in texts


def test_a_ruled_table_becomes_rows_and_is_not_repeated_as_prose(
    tmp_path: Path, write_pdf: Callable[[Sequence[dict[str, Any]]], bytes]
) -> None:
    source = _pdf(tmp_path / "report.pdf", write_pdf(REPORT_PAGES))

    extracted = PdfExtractor().extract(source)

    rows = [b for b in extracted.blocks if b.kind == BlockKind.TABLE_ROW]
    assert [b.text for b in rows] == ["ID\tSystem", "IF-01\tKUROSHIO"]
    assert rows[1].payload["cells"] == ["IF-01", "KUROSHIO"]
    # The same content must not also arrive as a paragraph.
    paragraphs = [b.text for b in extracted.blocks if b.kind == BlockKind.PARAGRAPH]
    assert not [text for text in paragraphs if "KUROSHIO" in text]


def test_every_block_traces_back_to_a_page_and_a_box(
    tmp_path: Path, write_pdf: Callable[[Sequence[dict[str, Any]]], bytes]
) -> None:
    source = _pdf(tmp_path / "report.pdf", write_pdf(REPORT_PAGES))

    extracted = PdfExtractor().extract(source)

    for block in extracted.blocks:
        assert block.source.kind == "pdf"
        assert block.source.page_number >= 1
        assert block.source.bbox is not None
    assert [container.title for container in extracted.containers] == [
        "Page 1",
        "Page 2",
        "Page 3",
    ]
    assert extracted.metadata["page_count"] == 3


def test_a_page_without_text_is_reported_not_silently_empty(
    tmp_path: Path, write_pdf: Callable[[Sequence[dict[str, Any]]], bytes]
) -> None:
    source = _pdf(tmp_path / "report.pdf", write_pdf(REPORT_PAGES))

    extracted = PdfExtractor().extract(source)

    warning = next(w for w in extracted.warnings if w.code == "pdf_page_without_text")
    assert warning.source is not None
    assert warning.source.page_number == 3
    assert "no OCR was performed" in warning.message


def test_an_embedded_image_is_extracted_with_its_media_type(
    tmp_path: Path, write_pdf_with_image: Callable[[bytes, int, int], bytes]
) -> None:
    buffer = io.BytesIO()
    Image.new("RGB", (16, 16), "red").save(buffer, "JPEG")
    source = _pdf(tmp_path / "image.pdf", write_pdf_with_image(buffer.getvalue(), 16, 16))

    extracted = PdfExtractor().extract(source)

    assert len(extracted.visuals) == 1
    visual = extracted.visuals[0]
    assert visual.media_type == "image/jpeg"
    assert visual.data.startswith(b"\xff\xd8")
    assert (visual.width, visual.height) == (16, 16)


def test_a_password_protected_file_is_refused_with_an_answerable_error(
    tmp_path: Path, write_pdf: Callable[[Sequence[dict[str, Any]]], bytes]
) -> None:
    plain = write_pdf([{"lines": [(72, 720, 11, "secret")]}])
    writer = pypdf.PdfWriter()
    writer.append(pypdf.PdfReader(io.BytesIO(plain)))
    writer.encrypt("pw")
    buffer = io.BytesIO()
    writer.write(buffer)
    source = _pdf(tmp_path / "locked.pdf", buffer.getvalue())

    with pytest.raises(EncryptedDocumentError, match="password-protected"):
        PdfExtractor().extract(source)


def test_too_many_pages_is_refused_before_parsing(
    tmp_path: Path, write_pdf: Callable[[Sequence[dict[str, Any]]], bytes]
) -> None:
    source = _pdf(tmp_path / "long.pdf", write_pdf(REPORT_PAGES))

    with pytest.raises(UnsafePackageError, match="3 pages"):
        PdfExtractor(PdfLimits(max_pages=2)).extract(source)
