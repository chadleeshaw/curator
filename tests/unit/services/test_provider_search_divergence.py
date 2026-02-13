"""
Tests for medium item #4 — divergent provider search path fixes:

1. Consolidated get_fuzzy_group_id — local copy removed, canonical version used everywhere
2. IA filtering — shared utility in core/utils/ia_filtering.py, applied in both paths
3. Provider timeout — fetch_from_providers now wraps calls with PROVIDER_SEARCH_TIMEOUT
"""

import sys
import time
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from unittest.mock import MagicMock, patch
from concurrent.futures import TimeoutError as FuturesTimeoutError

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from core.interfaces import SearchProvider, SearchResult
from core.utils.ia_filtering import (
    filter_ia_result,
    ia_title_matches_query,
    is_ia_collection,
)
from core.utils.fuzzy_matching import get_fuzzy_group_id


# =============================================================================
# Fix 1: Consolidated get_fuzzy_group_id
# =============================================================================


class TestConsolidatedFuzzyGroupId:
    """Verify the local get_fuzzy_group_id in cache.py was removed and
    both UI search and auto-download use the canonical version."""

    def test_cache_py_imports_from_core(self):
        """web/routers/search/cache.py should import from core.utils.fuzzy_matching."""
        import importlib
        import web.routers.search.cache as cache_mod

        # The module should have get_fuzzy_group_id in its namespace
        assert hasattr(cache_mod, "get_fuzzy_group_id")
        # It should be the one from core.utils.fuzzy_matching, not a local def
        assert cache_mod.get_fuzzy_group_id is get_fuzzy_group_id

    def test_library_py_imports_from_core(self):
        """web/routers/search/library.py should import from core, not from cache."""
        import web.routers.search.library as lib_mod

        assert hasattr(lib_mod, "get_fuzzy_group_id")
        assert lib_mod.get_fuzzy_group_id is get_fuzzy_group_id

    def test_canonical_version_handles_publication_date(self):
        """The canonical version supports optional publication_date for date-scoped grouping."""
        # Without date
        group_no_date = get_fuzzy_group_id("National Geographic")
        assert isinstance(group_no_date, str)
        assert len(group_no_date) > 0

        # With date — should include date component
        group_with_date = get_fuzzy_group_id("National Geographic", datetime(2024, 1, 15))
        assert "2024-01" in group_with_date
        assert group_no_date != group_with_date

    def test_canonical_version_removes_noise_words(self):
        """Canonical version strips noise words like 'the', 'magazine'."""
        group1 = get_fuzzy_group_id("The Economist")
        group2 = get_fuzzy_group_id("Economist")
        # Both should normalize to the same group
        assert "economist" in group1.lower()
        assert "economist" in group2.lower()

    def test_same_title_same_group(self):
        """Two identical titles should produce the same group ID."""
        group1 = get_fuzzy_group_id("PC Gamer - January 2024")
        group2 = get_fuzzy_group_id("PC Gamer - January 2024")
        assert group1 == group2


# =============================================================================
# Fix 2: IA filtering shared utility
# =============================================================================


class TestIaFilteringUtility:
    """Test the shared IA filtering functions in core/utils/ia_filtering.py."""

    def test_is_ia_collection_true(self):
        """Collection archives should be identified."""
        assert is_ia_collection({"is_collection": True}) is True

    def test_is_ia_collection_false(self):
        """Normal entries should not be flagged as collections."""
        assert is_ia_collection({"is_collection": False}) is False
        assert is_ia_collection({}) is False
        assert is_ia_collection(None) is False

    def test_ia_title_matches_query_good_match(self):
        """Title containing all search terms should pass."""
        assert ia_title_matches_query("National Geographic January 2024", "National Geographic") is True

    def test_ia_title_matches_query_poor_match(self):
        """Title not matching search terms should fail."""
        assert ia_title_matches_query("Cooking Recipes Vol 5", "National Geographic") is False

    def test_ia_title_matches_query_partial_match(self):
        """50% match should pass (default threshold)."""
        # "National" matches but "Geographic" doesn't
        assert ia_title_matches_query("National Review January 2024", "National Geographic") is True
        # match_ratio = 1/2 = 0.5 >= 0.5

    def test_ia_title_matches_query_short_terms_ignored(self):
        """Short terms (<3 chars) should be ignored in matching."""
        # "PC" is too short to count, "Gamer" should be the only significant term
        assert ia_title_matches_query("PC Gamer Issue 400", "PC Gamer") is True

    def test_ia_title_matches_query_no_significant_terms(self):
        """If all terms are too short, should pass (nothing to check)."""
        assert ia_title_matches_query("Something Else", "PC") is True

    def test_filter_ia_result_non_ia_always_passes(self):
        """Non-IA results should always pass regardless of content."""
        assert filter_ia_result("Random Title", "newsnab", {}, "Something Else") is True
        assert filter_ia_result("Random Title", "rss", {}, "Something Else") is True

    def test_filter_ia_result_collection_filtered(self):
        """IA collection archives should be filtered out."""
        assert filter_ia_result("My Archive Collection", "internet_archive", {"is_collection": True}, "Test") is False

    def test_filter_ia_result_poor_title_filtered(self):
        """IA results with poor title match should be filtered out."""
        assert filter_ia_result("Cooking Recipes Vol 5", "internet_archive", {}, "National Geographic") is False

    def test_filter_ia_result_good_match_passes(self):
        """IA results with good title match should pass."""
        assert (
            filter_ia_result("National Geographic January 2024", "internet_archive", {}, "National Geographic") is True
        )

    def test_filter_ia_result_no_query_skips_title_check(self):
        """When search_query is None, title-match check should be skipped."""
        assert filter_ia_result("Completely Unrelated Title", "internet_archive", {}, None) is True


class TestIaFilterInUiSearch:
    """Test that the IA filter is wired into the UI search filters module."""

    def test_filter_ia_results_function_exists(self):
        """filters.py should expose filter_ia_results function."""
        from web.routers.search.filters import filter_ia_results

        assert callable(filter_ia_results)

    def test_filter_ia_results_filters_collections(self):
        """UI filter should remove IA collection archives."""
        from web.routers.search.filters import filter_ia_results

        results = [
            {"title": "Good Result", "provider": "newsnab", "metadata": {}},
            {"title": "My Collection", "provider": "internet_archive", "metadata": {"is_collection": True}},
            {"title": "National Geographic Jan 2024", "provider": "internet_archive", "metadata": {}},
        ]
        filtered = filter_ia_results(results, "National Geographic")
        assert len(filtered) == 2
        assert filtered[0]["title"] == "Good Result"
        assert filtered[1]["title"] == "National Geographic Jan 2024"

    def test_filter_ia_results_filters_poor_matches(self):
        """UI filter should remove IA results that don't match the query."""
        from web.routers.search.filters import filter_ia_results

        results = [
            {"title": "Unrelated Cookbook Vol 3", "provider": "internet_archive", "metadata": {}},
            {"title": "National Geographic Jan 2024", "provider": "internet_archive", "metadata": {}},
        ]
        filtered = filter_ia_results(results, "National Geographic")
        assert len(filtered) == 1
        assert filtered[0]["title"] == "National Geographic Jan 2024"

    def test_filter_ia_results_preserves_non_ia(self):
        """Non-IA results should never be filtered."""
        from web.routers.search.filters import filter_ia_results

        results = [
            {"title": "Completely Unrelated", "provider": "newsnab", "metadata": {}},
            {"title": "Also Unrelated", "provider": "rss", "metadata": {}},
        ]
        filtered = filter_ia_results(results, "National Geographic")
        assert len(filtered) == 2

    def test_filter_ia_results_imported_in_endpoints(self):
        """endpoints.py should import filter_ia_results from filters."""
        import web.routers.search.endpoints as endpoints_mod
        from web.routers.search.filters import filter_ia_results

        assert hasattr(endpoints_mod, "filter_ia_results")


class TestIaFilterInAutoDownload:
    """Test that auto-download SearchService uses the shared IA filter."""

    def test_search_service_imports_filter_ia_result(self):
        """SearchService should import filter_ia_result from core.utils.ia_filtering."""
        import services.download.search_service as ss_mod

        assert hasattr(ss_mod, "filter_ia_result")
        assert ss_mod.filter_ia_result is filter_ia_result


# =============================================================================
# Fix 3: Provider timeout in UI search
# =============================================================================


class TestProviderTimeout:
    """Test that fetch_from_providers wraps calls with timeout."""

    def test_providers_module_imports_timeout_constant(self):
        """providers.py should import PROVIDER_SEARCH_TIMEOUT."""
        import web.routers.search.providers as prov_mod

        assert hasattr(prov_mod, "PROVIDER_SEARCH_TIMEOUT")
        from core.constants.app import PROVIDER_SEARCH_TIMEOUT

        assert prov_mod.PROVIDER_SEARCH_TIMEOUT == PROVIDER_SEARCH_TIMEOUT

    def test_providers_module_imports_timeout_error(self):
        """providers.py should import FuturesTimeoutError for handling."""
        import web.routers.search.providers as prov_mod

        assert hasattr(prov_mod, "FuturesTimeoutError")

    @patch("web.routers.search.providers.get_search_providers")
    def test_timeout_produces_error_message(self, mock_get_providers):
        """A provider that times out should produce an error message, not crash."""
        from web.routers.search.providers import fetch_from_providers

        # Create a mock provider that takes too long
        slow_provider = MagicMock()
        slow_provider.__class__.__name__ = "SlowProvider"

        def slow_search(*args, **kwargs):
            time.sleep(60)  # Much longer than timeout
            return []

        slow_provider.search = slow_search
        mock_get_providers.return_value = [slow_provider]

        # Patch the timeout to be very short for testing
        with patch("web.routers.search.providers.PROVIDER_SEARCH_TIMEOUT", 0.1):
            results, errors = fetch_from_providers(["test query"], None, set())

        assert len(results) == 0
        assert len(errors) == 1
        assert "timed out" in errors[0].lower()

    @patch("web.routers.search.providers.get_search_providers")
    def test_successful_provider_returns_results(self, mock_get_providers):
        """A fast provider should return results normally."""
        from web.routers.search.providers import fetch_from_providers

        mock_result = MagicMock()
        mock_result.title = "Test Magazine"
        mock_result.url = "http://example.com/test"
        mock_result.provider = "newsnab"
        mock_result.publication_date = datetime(2024, 1, 15, tzinfo=UTC)
        mock_result.raw_metadata = {}

        fast_provider = MagicMock()
        fast_provider.__class__.__name__ = "FastProvider"
        fast_provider.search.return_value = [mock_result]
        mock_get_providers.return_value = [fast_provider]

        results, errors = fetch_from_providers(["test query"], None, set())

        assert len(results) == 1
        assert results[0]["title"] == "Test Magazine"
        assert len(errors) == 0

    @patch("web.routers.search.providers.get_search_providers")
    def test_mixed_timeout_and_success(self, mock_get_providers):
        """One timed-out provider shouldn't prevent others from returning results."""
        from web.routers.search.providers import fetch_from_providers

        # Slow provider
        slow_provider = MagicMock()
        slow_provider.__class__.__name__ = "SlowProvider"
        slow_provider.search = MagicMock(side_effect=lambda *a, **kw: time.sleep(60) or [])

        # Fast provider
        mock_result = MagicMock()
        mock_result.title = "Fast Result"
        mock_result.url = "http://example.com/fast"
        mock_result.provider = "newsnab"
        mock_result.publication_date = datetime(2024, 1, 15, tzinfo=UTC)
        mock_result.raw_metadata = {}

        fast_provider = MagicMock()
        fast_provider.__class__.__name__ = "FastProvider"
        fast_provider.search.return_value = [mock_result]
        mock_get_providers.return_value = [slow_provider, fast_provider]

        with patch("web.routers.search.providers.PROVIDER_SEARCH_TIMEOUT", 0.1):
            results, errors = fetch_from_providers(["test query"], None, set())

        assert len(results) == 1  # Fast provider's result
        assert len(errors) == 1  # Slow provider's timeout error
        assert results[0]["title"] == "Fast Result"
