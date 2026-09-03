"""Independent semantic and presentation hashing for incremental updates."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from doc_agent.domain.models import Block


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")


def hash_semantic(block: Block) -> str:
    """Hash only agent-visible semantics; presentation-only edits must not change it."""

    return hashlib.sha256(
        _canonical({"kind": block.kind.value, "text": block.text, "payload": block.payload})
    ).hexdigest()


def hash_presentation(block: Block) -> str:
    """Hash layout/style/source-position metadata independently from semantics."""

    return hashlib.sha256(
        _canonical(
            {
                "presentation": block.presentation,
                "source": block.source.model_dump(mode="json"),
                "visual_required": block.visual_required,
            }
        )
    ).hexdigest()
