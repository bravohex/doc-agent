"""Stable identity helpers used across extraction and versioning."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Sequence
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
        [
            normalize_identity(format_name),
            normalize_identity(container),
            normalize_identity(identity),
        ]
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]
    hint_digest = hashlib.sha256(normalize_identity(hint).encode("utf-8")).hexdigest()[:6]
    return f"{format_name}:{digest}:{hint_digest}"


def deterministic_block_id(document_id: str, key: str) -> str:
    """Return the same block ID for a stable key across document versions."""

    return str(uuid5(NAMESPACE, f"{document_id}:{key}"))


def unique_stable_keys(keys: Sequence[str]) -> list[str]:
    """Disambiguate repeated stable keys deterministically, in document order.

    Structurally identical content — two identical paragraphs under one heading, two
    table rows sharing a first cell, two slides with the same title — legitimately
    produces the same identity seed. Persistence keeps one row per (version, stable
    key), so a repeat has to become its own key instead of aborting the whole ingest.
    The first occurrence keeps the unsuffixed key, so identities that were never
    ambiguous stay unchanged across versions.
    """

    emitted: set[str] = set()
    occurrences: dict[str, int] = {}
    result: list[str] = []
    for key in keys:
        candidate = key
        while candidate in emitted:
            occurrences[key] = occurrences.get(key, 1) + 1
            candidate = f"{key}#{occurrences[key]}"
        emitted.add(candidate)
        result.append(candidate)
    return result
