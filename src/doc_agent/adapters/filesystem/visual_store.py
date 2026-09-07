"""Content-addressed binary storage for extracted visual assets."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class VisualFile:
    sha256: str
    path: Path
    media_type: str


_EXTENSIONS = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/svg+xml": ".svg",
    "image/webp": ".webp",
}


class FileVisualStore:
    """Store identical binary content once regardless of source document."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, data: bytes, *, media_type: str) -> VisualFile:
        digest = hashlib.sha256(data).hexdigest()
        extension = _EXTENSIONS.get(media_type, ".bin")
        path = self.root / digest[:2] / f"{digest}{extension}"
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(data)
        return VisualFile(sha256=digest, path=path, media_type=media_type)

    def discard(self, stored_path: str) -> None:
        """Delete one stored file, ignoring a path that is already gone.

        The caller decides what is unreferenced; content is shared between documents,
        so this must never be handed a path another document still points at. Anything
        outside the store is refused rather than followed.
        """

        path = Path(stored_path)
        try:
            path.relative_to(self.root)
        except ValueError:
            return
        path.unlink(missing_ok=True)
        parent = path.parent
        if parent != self.root and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
