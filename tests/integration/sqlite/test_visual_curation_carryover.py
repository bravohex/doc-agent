"""Human curation of visuals must survive re-ingesting the document."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.drawing.image import Image as XlsxImage
from PIL import Image

from doc_agent.bootstrap import build_container


def _workbook(path: Path, image: Path, value: str, anchor: str = "C3") -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet["A1"] = value
    sheet.add_image(XlsxImage(image), anchor)
    workbook.save(path)


def test_annotations_survive_a_new_version(tmp_path: Path) -> None:
    image = tmp_path / "logo.png"
    Image.new("RGB", (8, 8), "white").save(image)
    source = tmp_path / "book.xlsx"
    _workbook(source, image, "one")

    app = build_container(tmp_path / "home")
    project = app.projects.create("Curation")
    first = app.ingest.execute(project.id, source)
    visual = app.repository.list_visuals(first.document_id)[0]
    app.repository.update_visual(
        visual["id"], decorative=True, retrieval_enabled=False, summary="company logo"
    )

    _workbook(source, image, "two")
    second = app.ingest.execute(project.id, source, replace_document_id=first.document_id)
    assert second.version_number == 2

    carried = app.repository.list_visuals(first.document_id)[0]
    assert carried["decorative"] == 1
    assert carried["retrieval_enabled"] == 0
    assert carried["summary"] == "company logo"


def test_a_moved_visual_keeps_its_annotations_through_the_content_hash(tmp_path: Path) -> None:
    image = tmp_path / "logo.png"
    Image.new("RGB", (8, 8), "white").save(image)
    source = tmp_path / "book.xlsx"
    _workbook(source, image, "one", anchor="C3")

    app = build_container(tmp_path / "home")
    project = app.projects.create("Moved")
    first = app.ingest.execute(project.id, source)
    visual = app.repository.list_visuals(first.document_id)[0]
    app.repository.update_visual(
        visual["id"], decorative=True, retrieval_enabled=False, summary="company logo"
    )

    _workbook(source, image, "one", anchor="H12")
    app.ingest.execute(project.id, source, replace_document_id=first.document_id)

    carried = app.repository.list_visuals(first.document_id)[0]
    assert carried["summary"] == "company logo"
    assert carried["decorative"] == 1


def test_a_fresh_visual_keeps_the_extractor_defaults(tmp_path: Path) -> None:
    image = tmp_path / "logo.png"
    Image.new("RGB", (8, 8), "white").save(image)
    source = tmp_path / "book.xlsx"
    _workbook(source, image, "one")

    app = build_container(tmp_path / "home")
    project = app.projects.create("Fresh")
    result = app.ingest.execute(project.id, source)

    visual = app.repository.list_visuals(result.document_id)[0]
    assert visual["decorative"] == 0
    assert visual["retrieval_enabled"] == 1
    assert visual["summary"] is None
