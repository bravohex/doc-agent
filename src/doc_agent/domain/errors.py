"""Domain errors exposed consistently across UI, CLI, and MCP adapters."""

from __future__ import annotations


class DocAgentError(Exception):
    """Base exception for expected application failures."""


class UnsupportedFormatError(DocAgentError):
    """Raised when no extractor supports a source file."""


class UnsafePackageError(DocAgentError):
    """Raised when an OOXML ZIP violates configured safety limits."""


class NotFoundError(DocAgentError):
    """Raised when a requested project, document, version, or block is missing."""


class VersionConflictError(DocAgentError):
    """Raised when a replacement cannot be reconciled with current state."""
