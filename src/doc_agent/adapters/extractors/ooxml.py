"""Safe, read-only OOXML ZIP inspection utilities."""

from __future__ import annotations

import posixpath
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from doc_agent.adapters.extractors.failures import readable
from doc_agent.domain.errors import UnsafePackageError


@dataclass(frozen=True, slots=True)
class OoxmlLimits:
    """Resource bounds applied before any high-level Office parser runs."""

    max_entries: int = 20_000
    max_total_uncompressed: int = 1_000_000_000
    max_entry_uncompressed: int = 100_000_000


class SafeOoxmlPackage:
    """Inspect OOXML archives without extracting paths to the filesystem."""

    def __init__(self, path: Path, *, limits: OoxmlLimits | None = None) -> None:
        self.path = path
        self.limits = limits or OoxmlLimits()

    def inspect(self) -> list[zipfile.ZipInfo]:
        with readable(self.path, "OOXML package"), zipfile.ZipFile(self.path) as archive:
            infos = archive.infolist()
            if len(infos) > self.limits.max_entries:
                raise UnsafePackageError(f"OOXML package has {len(infos)} entries")
            total = 0
            for info in infos:
                normalized = PurePosixPath(info.filename)
                if normalized.is_absolute() or ".." in normalized.parts:
                    raise UnsafePackageError(f"Unsafe OOXML entry path: {info.filename}")
                if info.file_size > self.limits.max_entry_uncompressed:
                    raise UnsafePackageError(f"OOXML entry too large: {info.filename}")
                total += info.file_size
                if total > self.limits.max_total_uncompressed:
                    raise UnsafePackageError("OOXML package exceeds uncompressed-size limit")
            return infos

    def read(self, part: str) -> bytes:
        self.inspect()
        with readable(self.path, "OOXML package"), zipfile.ZipFile(self.path) as archive:
            return archive.read(part)

    @staticmethod
    def resolve_target(base_part: str, target: str) -> str:
        """Resolve an OOXML relationship target while preventing path escape."""

        if target.startswith("/"):
            resolved = target.lstrip("/")
        else:
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(base_part), target))
        if resolved == ".." or resolved.startswith("../"):
            raise UnsafePackageError(f"Relationship escapes OOXML package: {target}")
        return resolved
