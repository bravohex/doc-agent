from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from doc_agent.adapters.extractors.ooxml import OoxmlLimits, SafeOoxmlPackage
from doc_agent.domain.errors import UnsafePackageError


def test_rejects_path_traversal(tmp_path: Path) -> None:
    path = tmp_path / "bad.xlsx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("../evil.xml", "x")
    with pytest.raises(UnsafePackageError):
        SafeOoxmlPackage(path).inspect()


def test_rejects_excessive_uncompressed_size(tmp_path: Path) -> None:
    path = tmp_path / "big.xlsx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/a.xml", "x" * 100)
    limits = OoxmlLimits(max_entries=10, max_total_uncompressed=50, max_entry_uncompressed=200)
    with pytest.raises(UnsafePackageError):
        SafeOoxmlPackage(path, limits=limits).inspect()
