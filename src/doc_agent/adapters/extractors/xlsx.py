# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportMissingTypeArgument=false, reportAttributeAccessIssue=false, reportPrivateUsage=false, reportCallIssue=false, reportArgumentType=false
# Dynamic third-party Office/UI APIs expose incomplete static types; strict checking remains enabled for domain, application, ports, and typed adapters.
"""High-fidelity XLSX extraction into compact row blocks plus sparse cell metadata."""

from __future__ import annotations

import datetime as dt
import mimetypes
from pathlib import Path
from typing import Any, ClassVar

from openpyxl import load_workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.utils import get_column_letter

from doc_agent.adapters.extractors.ooxml import SafeOoxmlPackage
from doc_agent.domain.identifiers import normalize_identity, stable_key
from doc_agent.domain.models import (
    Block,
    BlockKind,
    Container,
    ExtractedDocument,
    ExtractedVisual,
    XlsxLocator,
)


class XlsxExtractor:
    """Extract spreadsheet values without collapsing raw, cached, and display representations."""

    name = "xlsx"
    version = "1.0"
    suffixes: ClassVar[frozenset[str]] = frozenset({".xlsx", ".xlsm", ".xltx", ".xltm"})

    def supports(self, source: Path) -> bool:
        return source.suffix.lower() in self.suffixes

    def extract(self, source: Path) -> ExtractedDocument:
        SafeOoxmlPackage(source).inspect()
        formula_wb = load_workbook(source, data_only=False, read_only=False)
        cached_wb = load_workbook(source, data_only=True, read_only=False)
        blocks: list[Block] = []
        containers: list[Container] = []
        visuals: list[ExtractedVisual] = []

        for sheet_no, ws in enumerate(formula_wb.worksheets, start=1):
            cached_ws = cached_wb[ws.title]
            container_key = stable_key("xlsx", "workbook", ws.title)
            locator = XlsxLocator(sheet=ws.title, row=1, cell_range=ws.dimensions)
            tables = [{"name": table.name, "ref": table.ref} for table in ws.tables.values()]
            containers.append(
                Container(
                    stable_key=container_key,
                    kind="worksheet",
                    title=ws.title,
                    ordinal=sheet_no,
                    source=locator,
                    metadata={
                        "state": ws.sheet_state,
                        "dimension": ws.dimensions,
                        "tables": tables,
                    },
                )
            )
            merged_lookup: dict[str, str] = {}
            for merged in ws.merged_cells.ranges:
                for row in ws.iter_rows(
                    min_row=merged.min_row,
                    max_row=merged.max_row,
                    min_col=merged.min_col,
                    max_col=merged.max_col,
                ):
                    for cell in row:
                        merged_lookup[cell.coordinate] = merged.coord

            # Row coordinates are intentionally excluded from stable identity. A row that is
            # physically moved by inserting content above it must remain the same semantic block.
            # For duplicate first-column identities we keep a deterministic occurrence number;
            # truly indistinguishable duplicate rows cannot be matched more precisely without a
            # durable business identifier supplied by the workbook itself.
            row_identity_occurrences: dict[str, int] = {}
            for row_no in range(1, ws.max_row + 1):
                row_cells: list[dict[str, Any]] = []
                display_values: list[str] = []
                first_identity: str | None = None
                for col_no in range(1, ws.max_column + 1):
                    cell = ws.cell(row_no, col_no)
                    if isinstance(cell, MergedCell):
                        continue
                    cached = cached_ws.cell(row_no, col_no).value
                    has_metadata = bool(
                        cell.comment or cell.hyperlink or cell.coordinate in merged_lookup
                    )
                    if cell.value is None and cached is None and not has_metadata:
                        continue
                    formula = cell.value if cell.data_type == "f" else None
                    raw_value = None if formula is not None else self._json_value(cell.value)
                    display = self._display(
                        cached if formula is not None else cell.value, cell.number_format
                    )
                    if display:
                        display_values.append(display)
                    if first_identity is None and cell.value not in (None, ""):
                        first_identity = normalize_identity(cell.value)
                    row_cells.append(
                        {
                            "coordinate": cell.coordinate,
                            "raw_value": raw_value,
                            "formula": formula,
                            "cached_value": self._json_value(cached)
                            if formula is not None
                            else None,
                            "data_type": cell.data_type,
                            "number_format": cell.number_format,
                            "display": display,
                            "hyperlink": cell.hyperlink.target if cell.hyperlink else None,
                            "comment": cell.comment.text if cell.comment else None,
                            "merged_range": merged_lookup.get(cell.coordinate),
                            "hidden_column": bool(
                                ws.column_dimensions[get_column_letter(col_no)].hidden
                            ),
                        }
                    )
                if not row_cells:
                    continue
                identity = first_identity or f"content:{'|'.join(display_values)[:120]}"
                occurrence = row_identity_occurrences.get(identity, 0) + 1
                row_identity_occurrences[identity] = occurrence
                row_locator = XlsxLocator(
                    sheet=ws.title,
                    row=row_no,
                    cell_range=f"A{row_no}:{get_column_letter(ws.max_column)}{row_no}",
                )
                blocks.append(
                    Block(
                        stable_key=stable_key("xlsx", ws.title, identity, hint=occurrence),
                        container_key=container_key,
                        kind=BlockKind.TABLE_ROW,
                        ordinal=row_no,
                        text="\t".join(display_values),
                        source=row_locator,
                        payload={"cells": row_cells},
                        presentation={"hidden_row": bool(ws.row_dimensions[row_no].hidden)},
                    )
                )

            for image_no, image in enumerate(getattr(ws, "_images", []), start=1):
                try:
                    data = image._data()  # openpyxl exposes no public binary accessor.
                except Exception:
                    continue
                media_type = (
                    mimetypes.guess_type(getattr(image, "path", "image.png"))[0] or "image/png"
                )
                anchor_row = getattr(getattr(image, "anchor", None), "_from", None)
                row = (anchor_row.row + 1) if anchor_row is not None else None
                visuals.append(
                    ExtractedVisual(
                        stable_key=stable_key(
                            "xlsx", ws.title, f"image:{image_no}", hint=row or ""
                        ),
                        media_type=media_type,
                        source=XlsxLocator(sheet=ws.title, row=row),
                        data=data,
                        width=int(image.width) if image.width else None,
                        height=int(image.height) if image.height else None,
                    )
                )

            for chart_no, chart in enumerate(getattr(ws, "_charts", []), start=1):
                title = self._chart_title(chart) or f"Chart {chart_no}"
                blocks.append(
                    Block(
                        stable_key=stable_key("xlsx", ws.title, f"chart:{chart_no}", hint=title),
                        container_key=container_key,
                        kind=BlockKind.CHART,
                        ordinal=ws.max_row + chart_no,
                        text=title,
                        source=XlsxLocator(sheet=ws.title),
                        payload={"series_count": len(getattr(chart, "ser", []))},
                        visual_required=True,
                    )
                )

        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        return ExtractedDocument(
            logical_name=source.name,
            media_type=media_type,
            source_path=str(source),
            containers=containers,
            blocks=blocks,
            visuals=visuals,
            metadata={"sheet_count": len(formula_wb.worksheets)},
        )

    @staticmethod
    def _json_value(value: Any) -> Any:
        if isinstance(value, (dt.datetime, dt.date, dt.time)):
            return value.isoformat()
        return value

    @staticmethod
    def _display(value: Any, number_format: str) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        if isinstance(value, (dt.datetime, dt.date, dt.time)):
            return value.isoformat()
        if isinstance(value, (int, float)) and "%" in number_format:
            decimals = 0
            if "." in number_format:
                decimals = len(number_format.split(".", 1)[1].split("%", 1)[0])
            return f"{value * 100:.{decimals}f}%"
        return str(value)

    @staticmethod
    def _chart_title(chart: Any) -> str | None:
        try:
            rich = chart.title.tx.rich
            return "".join(run.t for p in rich.p for run in p.r if run.t).strip() or None
        except Exception:
            return None
