"""A project needs a handle a person can type, and these names are not all Latin.

Vietnamese survives with its diacritics stripped. A name written entirely in Japanese
leaves nothing to derive from, which is why a slug can also be given by hand.
"""

from __future__ import annotations

import pytest

from doc_agent.domain.slugs import (
    MAX_SLUG_LENGTH,
    InvalidSlugError,
    derive_slug,
    fallback_slug,
    normalize_slug,
    slugify,
)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("OLM Shopify Plus", "olm-shopify-plus"),
        ("RFP 2026 / v2", "rfp-2026-v2"),
        ("  spaced  out  ", "spaced-out"),
        ("Already-Hyphenated", "already-hyphenated"),
        # Vietnamese: diacritics are stripped and Đ is transliterated, not dropped.
        ("Đầu tư Việt Nam", "dau-tu-viet-nam"),
        ("ĐẤU THẦU", "dau-thau"),
        ("Nguyễn Hoàng", "nguyen-hoang"),
        # A mixed name keeps the part that can be read in Latin.
        ("MOG-001 (統合)", "mog-001"),
    ],
)
def test_slugify_keeps_names_readable(name: str, expected: str) -> None:
    assert slugify(name) == expected


@pytest.mark.parametrize("name", ["株式会社オークローン", "見積書", "   ", "***"])
def test_a_name_with_no_latin_text_slugifies_to_nothing(name: str) -> None:
    """Reported as empty so the caller can decide, rather than guessed at here."""

    assert slugify(name) == ""


def test_a_fallback_is_stable_and_reads_as_generated(name: str = "株式会社オークローン") -> None:
    handle = fallback_slug(name)

    assert handle == fallback_slug(name), "the same name must always give the same handle"
    assert handle.startswith("project-")
    assert normalize_slug(handle) == handle


def test_derive_slug_counts_up_rather_than_failing_on_a_repeated_name() -> None:
    """Two projects may legitimately share a name; the handle only has to be unambiguous."""

    assert derive_slug("OLM", taken=set()) == "olm"
    assert derive_slug("OLM", taken={"olm"}) == "olm-2"
    assert derive_slug("OLM", taken={"olm", "olm-2"}) == "olm-3"


def test_a_derived_slug_never_exceeds_the_length_limit() -> None:
    long_name = "Overall Migration " * 10

    handle = derive_slug(long_name, taken=set())
    counted = derive_slug(long_name, taken={handle})

    assert len(handle) <= MAX_SLUG_LENGTH
    assert len(counted) <= MAX_SLUG_LENGTH
    assert counted != handle


@pytest.mark.parametrize(
    ("given", "expected"),
    [("OLM-Plus", "olm-plus"), ("  olm  ", "olm"), ("mog2026", "mog2026")],
)
def test_normalize_slug_corrects_only_what_is_unambiguous(given: str, expected: str) -> None:
    assert normalize_slug(given) == expected


@pytest.mark.parametrize(
    "given",
    ["", "   ", "has space", "trailing-", "-leading", "double--hyphen", "Ünïcode", "a" * 61],
)
def test_a_slug_that_only_nearly_works_is_refused(given: str) -> None:
    """Two spellings of one handle in circulation is worse than an error."""

    with pytest.raises(InvalidSlugError):
        normalize_slug(given)
