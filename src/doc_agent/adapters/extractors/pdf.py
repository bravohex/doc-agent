# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportMissingTypeArgument=false, reportAttributeAccessIssue=false, reportPrivateUsage=false, reportCallIssue=false, reportArgumentType=false
# Dynamic third-party Office/UI APIs expose incomplete static types; strict checking remains enabled for domain, application, ports, and typed adapters.
"""PDF extraction that reports what the page states and infers no structure it lacks.

Two libraries do two jobs: pdfplumber reads text with its geometry and finds ruled
tables, while pypdf decodes embedded image XObjects back into usable bytes.
"""

from __future__ import annotations

import mimetypes
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pdfplumber
import pypdf

from doc_agent.adapters.extractors.failures import readable
from doc_agent.domain.errors import EncryptedDocumentError, UnsafePackageError
from doc_agent.domain.identifiers import stable_key
from doc_agent.domain.models import (
    Block,
    BlockKind,
    Container,
    ExtractedDocument,
    ExtractedVisual,
    ExtractionWarning,
    PdfLocator,
)

MEDIA_TYPE = "application/pdf"

# A wrapped line sits directly under its predecessor; a new paragraph leaves a visible
# gap. Comparing the gap against the line's own height keeps the rule font-size
# independent instead of hard-coding point values.
_PARAGRAPH_GAP_RATIO = 0.6
_SIZE_CHANGE = 0.5


@dataclass(frozen=True, slots=True)
class PdfLimits:
    """Resource bounds applied before any page is parsed."""

    max_pages: int = 5_000


@dataclass(frozen=True, slots=True)
class _Paragraph:
    text: str
    bbox: tuple[float, float, float, float]
    font_size: float


class PdfExtractor:
    """Extract page text, ruled tables, and embedded images without inventing headings."""

    name = "pdf"
    version = "1.0"

    def __init__(self, limits: PdfLimits | None = None) -> None:
        self.limits = limits or PdfLimits()

    def supports(self, source: Path) -> bool:
        return source.suffix.lower() == ".pdf"

    def extract(self, source: Path) -> ExtractedDocument:
        reader = self._reader(source)
        containers: list[Container] = []
        blocks: list[Block] = []
        warnings: list[ExtractionWarning] = []

        # Page content is parsed lazily, so the whole walk stays inside the guard.
        with readable(source, "PDF"), pdfplumber.open(source, password="") as pdf:
            for page in pdf.pages:
                number = int(page.page_number)
                container_key = stable_key("pdf", "document", f"page:{number}")
                tables = page.find_tables()
                paragraphs = self._paragraphs(page, tables)
                ordinal = 0

                containers.append(
                    Container(
                        stable_key=container_key,
                        kind="page",
                        title=f"Page {number}",
                        ordinal=number,
                        source=PdfLocator(page_number=number),
                        metadata={
                            "width": round(float(page.width), 2),
                            "height": round(float(page.height), 2),
                            "paragraph_count": len(paragraphs),
                            "table_count": len(tables),
                        },
                    )
                )

                for paragraph in paragraphs:
                    ordinal += 1
                    blocks.append(
                        Block(
                            # Page position stays out of the identity so text that reflows
                            # onto another page stays the same block.
                            stable_key=stable_key("pdf", "document", paragraph.text),
                            container_key=container_key,
                            kind=BlockKind.PARAGRAPH,
                            ordinal=number * 10_000 + ordinal,
                            text=paragraph.text,
                            source=PdfLocator(
                                page_number=number, block_index=ordinal, bbox=paragraph.bbox
                            ),
                            presentation={"font_size": paragraph.font_size},
                        )
                    )

                for table_no, table in enumerate(tables, start=1):
                    for row_no, cells, bbox in self._table_rows(table):
                        text = "\t".join(value for value in cells if value)
                        if not text:
                            continue
                        ordinal += 1
                        blocks.append(
                            Block(
                                stable_key=stable_key(
                                    "pdf",
                                    "document",
                                    cells[0] or text[:80],
                                    hint=f"table:{table_no}",
                                ),
                                container_key=container_key,
                                kind=BlockKind.TABLE_ROW,
                                ordinal=number * 10_000 + ordinal,
                                text=text,
                                source=PdfLocator(page_number=number, row_index=row_no, bbox=bbox),
                                payload={"cells": cells},
                            )
                        )

                if not paragraphs and not tables:
                    warnings.append(
                        ExtractionWarning(
                            code="pdf_page_without_text",
                            message=(
                                f"Page {number} carries no extractable text. It is most likely a "
                                "scan; no OCR was performed and nothing was inferred from it."
                            ),
                            source=PdfLocator(page_number=number),
                        )
                    )

        visuals = self._visuals(reader, warnings)
        return ExtractedDocument(
            logical_name=source.name,
            media_type=MEDIA_TYPE,
            source_path=str(source),
            containers=containers,
            blocks=blocks,
            visuals=visuals,
            warnings=warnings,
            metadata={"page_count": len(reader.pages)},
        )

    def _reader(self, source: Path) -> pypdf.PdfReader:
        """Open the file, refusing what cannot be read honestly."""

        with readable(source, "PDF"):
            reader = pypdf.PdfReader(source)
        if reader.is_encrypted and not self._unlock(reader):
            raise EncryptedDocumentError(
                f"PDF is password-protected and cannot be read: {source.name}"
            )
        with readable(source, "PDF"):
            page_count = len(reader.pages)
        if page_count > self.limits.max_pages:
            raise UnsafePackageError(f"PDF has {page_count} pages")
        return reader

    @staticmethod
    def _unlock(reader: pypdf.PdfReader) -> bool:
        """Some files are only owner-locked and open with an empty user password."""

        try:
            return bool(reader.decrypt(""))
        except Exception:
            return False

    @classmethod
    def _paragraphs(cls, page: Any, tables: list[Any]) -> list[_Paragraph]:
        """Group wrapped lines into paragraphs, leaving table content to the table pass."""

        boxes = [table.bbox for table in tables]
        paragraphs: list[_Paragraph] = []
        current: list[dict[str, Any]] = []
        previous: dict[str, Any] | None = None
        for line in page.extract_text_lines():
            if cls._inside(line, boxes):
                continue
            if current and previous is not None and cls._breaks(previous, line):
                paragraphs.append(cls._join(current))
                current = []
            current.append(line)
            previous = line
        if current:
            paragraphs.append(cls._join(current))
        return paragraphs

    @staticmethod
    def _inside(line: dict[str, Any], boxes: list[Any]) -> bool:
        middle = (float(line["top"]) + float(line["bottom"])) / 2
        return any(
            float(x0) <= float(line["x0"]) <= float(x1) and float(top) <= middle <= float(bottom)
            for x0, top, x1, bottom in boxes
        )

    @classmethod
    def _breaks(cls, previous: dict[str, Any], line: dict[str, Any]) -> bool:
        gap = float(line["top"]) - float(previous["bottom"])
        height = max(float(line["bottom"]) - float(line["top"]), 1.0)
        if gap > height * _PARAGRAPH_GAP_RATIO:
            return True
        return abs(cls._font_size(line) - cls._font_size(previous)) > _SIZE_CHANGE

    @staticmethod
    def _font_size(line: dict[str, Any]) -> float:
        sizes = [float(char["size"]) for char in line.get("chars", []) if char.get("size")]
        return round(statistics.median(sizes), 2) if sizes else 0.0

    @classmethod
    def _join(cls, lines: list[dict[str, Any]]) -> _Paragraph:
        return _Paragraph(
            # Lines of one paragraph are wrapping, not separate statements.
            text=" ".join(str(line["text"]).strip() for line in lines).strip(),
            bbox=(
                min(float(line["x0"]) for line in lines),
                min(float(line["top"]) for line in lines),
                max(float(line["x1"]) for line in lines),
                max(float(line["bottom"]) for line in lines),
            ),
            font_size=round(statistics.median([cls._font_size(line) for line in lines]), 2),
        )

    @staticmethod
    def _table_rows(table: Any) -> list[tuple[int, list[str], tuple[float, float, float, float]]]:
        extracted = table.extract()
        rows: list[tuple[int, list[str], tuple[float, float, float, float]]] = []
        for index, (cells, row) in enumerate(zip(extracted, table.rows, strict=True), start=1):
            values = [str(cell).strip() if cell is not None else "" for cell in cells]
            bbox = tuple(round(float(value), 2) for value in row.bbox)
            rows.append((index, values, bbox))
        return rows

    @classmethod
    def _visuals(
        cls, reader: pypdf.PdfReader, warnings: list[ExtractionWarning]
    ) -> list[ExtractedVisual]:
        visuals: list[ExtractedVisual] = []
        for number, page in enumerate(reader.pages, start=1):
            try:
                images = list(page.images)
            except Exception:
                warnings.append(cls._unreadable_images(number))
                continue
            for index, image in enumerate(images, start=1):
                try:
                    data = image.data
                except Exception:
                    warnings.append(cls._unreadable_images(number))
                    continue
                width, height = cls._dimensions(image)
                visuals.append(
                    ExtractedVisual(
                        stable_key=stable_key(
                            "pdf", f"page:{number}", f"image:{index}", hint=image.name
                        ),
                        media_type=mimetypes.guess_type(image.name)[0]
                        or "application/octet-stream",
                        source=PdfLocator(page_number=number),
                        data=data,
                        width=width,
                        height=height,
                    )
                )
        return visuals

    @staticmethod
    def _unreadable_images(page_number: int) -> ExtractionWarning:
        return ExtractionWarning(
            code="pdf_image_unreadable",
            message=(
                f"An embedded image on page {page_number} could not be decoded and was skipped "
                "rather than stored as unusable bytes."
            ),
            source=PdfLocator(page_number=page_number),
        )

    @staticmethod
    def _dimensions(image: Any) -> tuple[int | None, int | None]:
        try:
            width, height = image.image.size
        except Exception:
            return None, None
        return int(width), int(height)
