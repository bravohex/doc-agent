from __future__ import annotations

import ast
from pathlib import Path

import pytest

# Anchored to this file rather than the working directory. A relative path let the
# guard scan nothing and still pass, which silently disabled the boundary it protects.
SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src" / "doc_agent"

FORBIDDEN = {
    "domain": {
        "doc_agent.adapters",
        "doc_agent.interfaces",
        "nicegui",
        "openpyxl",
        "docx",
        "pptx",
        "pdfplumber",
        "pypdf",
        "sqlite3",
        "mcp",
        "typer",
    },
    "application": {
        "doc_agent.adapters",
        "doc_agent.interfaces",
        "nicegui",
        "openpyxl",
        "docx",
        "pptx",
        "pdfplumber",
        "pypdf",
        "sqlite3",
        "mcp",
        "typer",
    },
    "ports": {
        "doc_agent.adapters",
        "doc_agent.interfaces",
        "nicegui",
        "openpyxl",
        "docx",
        "pptx",
        "pdfplumber",
        "pypdf",
        "sqlite3",
    },
}


def _imports(file: Path) -> set[str]:
    tree = ast.parse(file.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def test_source_root_is_discoverable() -> None:
    """A boundary test that scans nothing must fail loudly, not pass quietly."""

    assert SOURCE_ROOT.is_dir(), SOURCE_ROOT
    assert len(list(SOURCE_ROOT.rglob("*.py"))) >= 20


@pytest.mark.parametrize("package", sorted(FORBIDDEN))
def test_dependency_boundaries(package: str) -> None:
    folder = SOURCE_ROOT / package
    files = sorted(folder.rglob("*.py"))
    assert files, f"no modules found under {folder}"
    for file in files:
        violations = sorted(
            imported
            for imported in _imports(file)
            if any(
                imported == item or imported.startswith(f"{item}.") for item in FORBIDDEN[package]
            )
        )
        assert not violations, f"{file}: forbidden imports {violations}"
