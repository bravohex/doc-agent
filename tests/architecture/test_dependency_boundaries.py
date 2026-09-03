from __future__ import annotations

import ast
from pathlib import Path


FORBIDDEN = {
    "doc_agent.domain": {"doc_agent.adapters", "doc_agent.interfaces", "nicegui", "openpyxl", "docx", "pptx", "sqlite3"},
    "doc_agent.application": {"doc_agent.adapters", "doc_agent.interfaces", "nicegui", "openpyxl", "docx", "pptx", "sqlite3"},
}


def test_dependency_boundaries() -> None:
    root = Path("src/doc_agent")
    for package, forbidden in FORBIDDEN.items():
        folder = root / package.split(".")[-1]
        for file in folder.rglob("*.py"):
            tree = ast.parse(file.read_text(encoding="utf-8"))
            imports: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.add(node.module)
            violations = sorted(
                imported
                for imported in imports
                if any(imported == item or imported.startswith(f"{item}.") for item in forbidden)
            )
            assert not violations, f"{file}: forbidden imports {violations}"
