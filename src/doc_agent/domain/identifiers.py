"""Stable identity helpers used across extraction and versioning."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from uuid import UUID, uuid5


NAMESPACE = UUID("8cfba366-4108-4af1-a504-97ec85132e60")


def normalize_identity(value: object) -> str:
    """Normalize source identifiers without guessing business semantics."""

    text = unicodedata.normalize("NFKC", str(value)).strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def stable_key(format_name: str, container: str, identity: object, *, hint: object = "") -> str:
    """Build a deterministic opaque key from structural and semantic identity.

    Ordinal positions are deliberately not accepted as a dedicated argument because
    inserted rows/slides would otherwise invalidate every subsequent identity.
    """

    seed = "\x1f".join(
        [normalize_identity(format_name), normalize_identity(container), normalize_identity(identity)]
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]
    hint_digest = hashlib.sha256(normalize_identity(hint).encode("utf-8")).hexdigest()[:6]
    return f"{format_name}:{digest}:{hint_digest}"


def deterministic_block_id(document_id: str, key: str) -> str:
    """Return the same block ID for a stable key across document versions."""

    return str(uuid5(NAMESPACE, f"{document_id}:{key}"))
