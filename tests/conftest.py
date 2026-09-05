"""Shared fixtures.

PDF fixtures are written by hand: no dependency creates PDFs, and a literal writer
keeps the bytes under test deterministic and readable.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import pytest

TextLine = tuple[float, float, float, str]
Rule = tuple[float, float, float, float]


def _escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _content(lines: Sequence[TextLine], rules: Sequence[Rule]) -> bytes:
    parts = [
        f"BT /F1 {size} Tf 1 0 0 1 {x} {y} Tm ({_escape(text)}) Tj ET" for x, y, size, text in lines
    ]
    parts += [f"{x0} {y0} m {x1} {y1} l S" for x0, y0, x1, y1 in rules]
    return "\n".join(parts).encode("latin-1")


def _assemble(objects: list[bytes]) -> bytes:
    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % index + body + b"\nendobj\n"
    xref_at = len(out)
    out += b"xref\n0 %d\n" % (len(objects) + 1)
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        xref_at,
    )
    return bytes(out)


def _write_pages(pages: Sequence[dict[str, Any]]) -> bytes:
    """Each page is {"lines": [(x, y, font_size, text)], "rules": [(x0, y0, x1, y1)]}."""

    objects: list[bytes] = [b"", b"", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids: list[int] = []
    for page in pages:
        stream = _content(page.get("lines", []), page.get("rules", []))
        objects.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        content_num = len(objects)
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % content_num
        )
        kids.append(len(objects))
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
        b" ".join(b"%d 0 R" % kid for kid in kids),
        len(kids),
    )
    return _assemble(objects)


def _write_image_page(jpeg: bytes, width: int, height: int) -> bytes:
    stream = b"q 120 0 0 120 72 600 cm /Im1 Do Q"
    return _assemble(
        [
            b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /XObject << /Im1 5 0 R >> >> /Contents 4 0 R >>",
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceRGB "
            b"/BitsPerComponent 8 /Filter /DCTDecode /Length %d >>\nstream\n"
            % (width, height, len(jpeg))
            + jpeg
            + b"\nendstream",
        ]
    )


@pytest.fixture
def write_pdf() -> Callable[[Sequence[dict[str, Any]]], bytes]:
    """Build a text/table PDF from page descriptions."""

    return _write_pages


@pytest.fixture
def write_pdf_with_image() -> Callable[[bytes, int, int], bytes]:
    """Build a one-page PDF holding a single JPEG image XObject."""

    return _write_image_page
