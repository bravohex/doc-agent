"""Readable handles for projects, so a person never has to type a UUID.

A project id is a UUID because it has to be stable and collision-free. That makes it
unusable in conversation, on a command line, or in a breadcrumb, so a project also
carries a slug derived from its name.

Names here are routinely Vietnamese and Japanese, which the derivation has to survive:
Vietnamese loses its diacritics and stays readable, while a name written entirely in
Japanese leaves no Latin characters at all and gets a generated handle instead. That
case is why a slug can also be given explicitly -- a generated one is unambiguous but
not memorable, and only the person naming the project can fix that.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

#: Latin letters, digits and single hyphens. Short enough to type, long enough to read.
MAX_SLUG_LENGTH = 60

_SEPARATORS = re.compile(r"[^A-Za-z0-9]+")
_VALID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

#: Đ/đ carry no combining mark to strip, so they are mapped before normalization.
_TRANSLITERATE = str.maketrans({"Đ": "D", "đ": "d", "Ð": "D", "ð": "d", "ø": "o", "Ø": "O"})


class InvalidSlugError(ValueError):
    """Raised when a slug given by hand cannot be used as a handle."""


def slugify(name: str) -> str:
    """Derive a handle from a name, or return "" when the name yields no Latin text."""

    folded = unicodedata.normalize("NFKD", name.translate(_TRANSLITERATE))
    stripped = "".join(char for char in folded if not unicodedata.combining(char))
    return _SEPARATORS.sub("-", stripped).strip("-").lower()[:MAX_SLUG_LENGTH].strip("-")


def fallback_slug(name: str) -> str:
    """Generate a stable handle for a name that slugifies to nothing.

    Derived from the name so the same name always yields the same handle, and prefixed
    so it reads as generated rather than as something the author chose.
    """

    digest = hashlib.sha256(name.strip().encode("utf-8")).hexdigest()[:6]
    return f"project-{digest}"


def normalize_slug(slug: str) -> str:
    """Validate a slug given by hand, naming what is wrong with it.

    Accepting a slug that only nearly works would leave two spellings of one handle in
    circulation, so it is corrected where that is unambiguous -- case and surrounding
    whitespace -- and refused otherwise.
    """

    candidate = slug.strip().lower()
    if not candidate:
        raise InvalidSlugError("Slug is empty")
    if len(candidate) > MAX_SLUG_LENGTH:
        raise InvalidSlugError(f"Slug is longer than {MAX_SLUG_LENGTH} characters: {slug!r}")
    if not _VALID.match(candidate):
        raise InvalidSlugError(
            f"Slug must be lowercase letters, digits and single hyphens: {slug!r}"
        )
    return candidate


def derive_slug(name: str, *, taken: set[str]) -> str:
    """Choose an unused handle for ``name``.

    A repeated name gets a counter rather than an error: two projects may legitimately
    share a name, and the handle only has to be unambiguous.
    """

    base = slugify(name) or fallback_slug(name)
    if base not in taken:
        return base
    for suffix in range(2, 1000):
        candidate = f"{base[: MAX_SLUG_LENGTH - len(str(suffix)) - 1].strip('-')}-{suffix}"
        if candidate not in taken:
            return candidate
    raise InvalidSlugError(f"Cannot derive an unused slug for {name!r}")
