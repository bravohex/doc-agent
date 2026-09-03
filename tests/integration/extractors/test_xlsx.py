from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.comments import Comment

from doc_agent.adapters.extractors.xlsx import XlsxExtractor
from doc_agent.domain.models import BlockKind


def test_xlsx_preserves_formula_format_comment_merge_and_hidden_metadata(tmp_path: Path) -> None:
    path = tmp_path / "sample.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "MOG"
    ws.append(["ID", "Function", "Rate", "Formula"])
    ws.append(["MOG-001", "PayPay", 0.125, "=3*4"])
    ws["C2"].number_format = "0.0%"
    ws["B2"].comment = Comment("business note", "OLM")
    ws.merge_cells("A4:C4")
    ws["A4"] = "Merged heading"
    ws.row_dimensions[2].hidden = True
    ws.column_dimensions["D"].hidden = True
    wb.save(path)

    doc = XlsxExtractor().extract(path)
    rows = [b for b in doc.blocks if b.kind == BlockKind.TABLE_ROW]
    assert any("PayPay" in b.text for b in rows)
    row = next(b for b in rows if "MOG-001" in b.text)
    cells = row.payload["cells"]
    rate = next(c for c in cells if c["coordinate"] == "C2")
    formula = next(c for c in cells if c["coordinate"] == "D2")
    comment = next(c for c in cells if c["coordinate"] == "B2")
    assert rate["raw_value"] == 0.125
    assert rate["display"] == "12.5%"
    assert formula["formula"] == "=3*4"
    assert comment["comment"] == "business note"
    assert row.presentation["hidden_row"] is True
    merged = next(b for b in rows if "Merged heading" in b.text)
    assert merged.payload["cells"][0]["merged_range"] == "A4:C4"
    assert len([c for c in merged.payload["cells"] if c["raw_value"] == "Merged heading"]) == 1
