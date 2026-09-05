"""A damaged or mislabelled file is a statement about the document, not a traceback."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from doc_agent.bootstrap import build_container
from doc_agent.domain.errors import CorruptDocumentError

EXTENSIONS = [".xlsx", ".docx", ".pptx", ".pdf"]


@pytest.mark.parametrize("extension", EXTENSIONS)
def test_a_file_that_is_not_its_extension_is_refused(tmp_path: Path, extension: str) -> None:
    source = tmp_path / f"broken{extension}"
    source.write_bytes(b"this is plain text, whatever the name says")
    app = build_container(tmp_path / "home")
    project = app.projects.create("Broken")

    with pytest.raises(CorruptDocumentError, match="cannot be read"):
        app.ingest.execute(project.id, source)


@pytest.mark.parametrize("extension", [".xlsx", ".docx", ".pptx"])
def test_a_zip_that_is_not_an_office_package_is_refused(tmp_path: Path, extension: str) -> None:
    source = tmp_path / f"plain{extension}"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("readme.txt", "a valid zip, but no Office parts")
    app = build_container(tmp_path / "home")
    project = app.projects.create("Broken")

    with pytest.raises(CorruptDocumentError, match="cannot be read"):
        app.ingest.execute(project.id, source)


def test_a_truncated_pdf_is_refused(tmp_path: Path, write_pdf) -> None:
    source = tmp_path / "cut.pdf"
    source.write_bytes(write_pdf([{"lines": [(72, 720, 11, "start")]}])[:120])
    app = build_container(tmp_path / "home")
    project = app.projects.create("Broken")

    with pytest.raises(CorruptDocumentError, match="cannot be read"):
        app.ingest.execute(project.id, source)
