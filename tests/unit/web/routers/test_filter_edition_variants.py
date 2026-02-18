"""
Tests for filter_periodical_variants in web/routers/search/filters.py.

Key terminology:
- "Editions" = individual issue numbers/volumes (Issue 1, Issue 2, Vol 3, etc.)
- "Variants" = the same issue available from multiple providers (deduplication targets)
- "Periodical variants" = geographically/demographically distinct periodicals
  (e.g. "Wired UK" vs "Wired US", "National Geographic" vs "National Geographic Kids")
"""

import sys
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

# Import only lightweight constants — no PIL/fitz/database deps
from core.constants.periodical import (
    AMBIGUOUS_ISO_CODES,
    AUDIENCE_PERIODICAL_INDICATORS,
    REGIONAL_PERIODICAL_INDICATORS,
)
from core.constants.country import ISO_COUNTRIES
from core.constants.title import MULTI_WORD_PERIODICAL_VARIANTS


def _extract_periodical_variant(title: str) -> Optional[str]:
    """
    Standalone re-implementation of TitleMatcher.extract_periodical_variant using
    the same constants, so tests don't need to import the full TitleMatcher
    (which pulls in PIL/fitz through core/parsers/__init__.py).
    """
    title_lower = title.lower()

    # Check multi-word variants first (e.g., "little kids", "young adult")
    for variant in MULTI_WORD_PERIODICAL_VARIANTS:
        if variant in title_lower:
            return variant

    words = title_lower.split()
    for i, word in enumerate(words):
        clean_word = word.strip(".,;:!?()[]{}\"'")

        # Skip "No 123", "Vol 5", etc.
        if i + 1 < len(words):
            next_word = words[i + 1].strip(".,;:!?()[]{}\"'")
            if clean_word in ["no", "vol", "volume", "issue", "v"] and next_word.isdigit():
                continue

        clean_word_upper = clean_word.upper()
        if clean_word_upper in ISO_COUNTRIES and clean_word_upper not in AMBIGUOUS_ISO_CODES:
            return clean_word

        if clean_word in REGIONAL_PERIODICAL_INDICATORS:
            return clean_word

    for word in words:
        clean_word = word.strip(".,;:!?()[]{}\"'")
        if clean_word in AUDIENCE_PERIODICAL_INDICATORS:
            return clean_word

    return None


@pytest.fixture(autouse=True)
def inject_title_matcher():
    """
    Inject a lightweight mock title matcher backed by the real constants-based logic.
    This avoids importing the full TitleMatcher class which pulls in PIL, fitz, etc.
    """
    mock_matcher = MagicMock()
    mock_matcher.extract_periodical_variant.side_effect = _extract_periodical_variant
    with patch("web.routers.search.filters.get_title_matcher", return_value=mock_matcher):
        yield


def _make_result(title: str) -> dict:
    return {"title": title, "url": f"http://example.com/{title}", "provider": "test"}


class TestRegionalQueryVariantFiltering:
    """
    Tests for the main fix: when the query has a regional (country/geography) variant,
    results without any variant should NOT be filtered out.

    Regression: searching 'Wired UK' was removing 509 results like 'Wired Issue 45'
    that were returned via the 'Wired' alias. These are real issues of Wired UK,
    just indexed without the regional suffix — not a different periodical.
    """

    def test_regional_query_keeps_no_variant_result(self):
        """Core fix: result with no regional suffix is kept when query has regional variant."""
        from web.routers.search.filters import filter_periodical_variants

        results = [_make_result("Wired Issue 45")]
        filtered = filter_periodical_variants(results, "Wired UK")
        assert len(filtered) == 1, "Issues without regional suffix should be kept for regional-variant queries"

    def test_regional_query_keeps_matching_variant_result(self):
        """Result with the same regional variant as the query is kept."""
        from web.routers.search.filters import filter_periodical_variants

        results = [_make_result("Wired UK Issue 45")]
        filtered = filter_periodical_variants(results, "Wired UK")
        assert len(filtered) == 1

    def test_regional_query_filters_conflicting_regional_variant(self):
        """Result with a different regional variant is filtered out."""
        from web.routers.search.filters import filter_periodical_variants

        results = [_make_result("Wired US Issue 45")]
        filtered = filter_periodical_variants(results, "Wired UK")
        assert len(filtered) == 0

    def test_us_regional_query_keeps_no_variant_result(self):
        """'US' regional variant query also keeps results without any variant."""
        from web.routers.search.filters import filter_periodical_variants

        results = [_make_result("PC Gamer Issue 5")]
        filtered = filter_periodical_variants(results, "PC Gamer US")
        assert len(filtered) == 1

    def test_mixed_results_only_conflicting_variants_filtered(self):
        """
        With a regional query, only results with a conflicting variant are removed.
        Results with no variant or the matching variant are both kept.
        """
        from web.routers.search.filters import filter_periodical_variants

        results = [
            _make_result("Wired UK Issue 45"),  # same regional variant → keep
            _make_result("Wired Issue 45"),  # no variant → keep (the fix)
            _make_result("Wired US Issue 45"),  # different regional variant → filter
        ]
        filtered = filter_periodical_variants(results, "Wired UK")
        assert len(filtered) == 2
        titles = [r["title"] for r in filtered]
        assert "Wired UK Issue 45" in titles
        assert "Wired Issue 45" in titles
        assert "Wired US Issue 45" not in titles


class TestNonRegionalQueryVariantFiltering:
    """
    Tests for queries with no variant or a non-regional (audience/specialization) variant.
    These cases retain the original strict-matching behavior.
    """

    def test_no_variant_query_filters_non_regional_variant_result(self):
        """When query has no variant, results with non-regional variants (kids, pro) are filtered."""
        from web.routers.search.filters import filter_periodical_variants

        results = [_make_result("National Geographic Kids")]
        filtered = filter_periodical_variants(results, "National Geographic")
        assert len(filtered) == 0

    def test_no_variant_query_filters_regional_variant_result(self):
        """When query has no variant, results with a regional variant are filtered."""
        from web.routers.search.filters import filter_periodical_variants

        results = [_make_result("National Geographic UK")]
        filtered = filter_periodical_variants(results, "National Geographic")
        assert len(filtered) == 0

    def test_non_regional_query_variant_filters_no_variant_result(self):
        """When query has a non-regional variant (Pro, Kids), no-variant results are filtered."""
        from web.routers.search.filters import filter_periodical_variants

        results = [_make_result("PC Gamer Issue 5")]
        filtered = filter_periodical_variants(results, "PC Gamer Pro")
        assert len(filtered) == 0

    def test_both_no_variant_kept(self):
        """When both query and result have no variant, result is kept."""
        from web.routers.search.filters import filter_periodical_variants

        results = [_make_result("National Geographic March 2024")]
        filtered = filter_periodical_variants(results, "National Geographic")
        assert len(filtered) == 1

    def test_same_non_regional_variant_kept(self):
        """When both query and result have the same non-regional variant, result is kept."""
        from web.routers.search.filters import filter_periodical_variants

        results = [_make_result("National Geographic Kids March 2024")]
        filtered = filter_periodical_variants(results, "National Geographic Kids")
        assert len(filtered) == 1
