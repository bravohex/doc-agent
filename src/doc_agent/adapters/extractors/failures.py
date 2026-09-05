"""Turn parser failures into answerable domain errors.

Office and PDF parsers raise their own exception types for a damaged, truncated, or
merely mislabelled file. Letting those reach the CLI, UI, or an MCP client hands over a
library traceback instead of a statement about the document, so every extractor funnels
its parsing through here.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from doc_agent.domain.errors import CorruptDocumentError, DocAgentError


@contextmanager
def readable(source: Path, label: str) -> Generator[None]:
    """Report an unparsable source as a corrupt document, never as a raw parser error."""

    try:
        yield
    except DocAgentError:
        raise
    except Exception as exc:
        raise CorruptDocumentError(
            f"{label} cannot be read; the file is damaged or is not the format its extension "
            f"claims: {source.name}"
        ) from exc
