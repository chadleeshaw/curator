"""
Tests for medium item #4 — divergent provider search path fixes:

1. Consolidated get_fuzzy_group_id — local copy removed, canonical version used everywhere
2. Result filtering — shared utility in core/utils/result_filter.py, applied in both paths
3. Provider timeout — fetch_from_providers now wraps calls with PROVIDER_SEARCH_TIMEOUT
"""

import sys
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from unittest.mock import MagicMock, patch
from concurrent.futures import TimeoutError as FuturesTimeoutError

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from core.interfaces import SearchProvider, SearchResult
from core.utils.result_filter import (
    _query_contains_collection_word,
    filter_result,
    title_matches_query,
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
        """Group IDs are title-based only — publication date is not included."""
        group = get_fuzzy_group_id("National Geographic")
        assert isinstance(group, str)
        assert len(group) > 0
        assert "2024" not in group

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
    """Test the shared result filtering functions in core/utils/result_filter.py."""

    def test_is_ia_collection_true(self):
        """Collection archives should be identified."""
        assert is_ia_collection({"is_collection": True}) is True

    def test_is_ia_collection_false(self):
        """Normal entries should not be flagged as collections."""
        assert is_ia_collection({"is_collection": False}) is False
        assert is_ia_collection({}) is False
        assert is_ia_collection(None) is False

    def test_title_matches_query_good_match(self):
        """Title containing all search terms should pass."""
        assert title_matches_query("National Geographic January 2024", "National Geographic") is True

    def test_title_matches_query_poor_match(self):
        """Title not matching search terms should fail."""
        assert title_matches_query("Cooking Recipes Vol 5", "National Geographic") is False

    def test_title_matches_query_partial_match_long_query(self):
        """50% match passes for queries with 3+ terms (uses default threshold)."""
        # 3-term query: "National Geographic Traveller"
        # "National Geographic" matches (2/3 = 66% >= 50%)
        assert title_matches_query("National Geographic January 2024", "National Geographic Traveller") is True

    def test_title_matches_query_partial_match_short_query_fails(self):
        """Partial matches fail for short queries (1-2 terms require 100% match)."""
        # 2-term query: "National Geographic"
        # "National Review" only has 1/2 terms (50% < 100% required) → fails
        assert title_matches_query("National Review January 2024", "National Geographic") is False

    def test_title_matches_query_short_terms_now_included(self):
        """Terms with 2+ chars are now checked (includes magazine abbreviations like PC, GQ)."""
        # Both "PC" and "Gamer" must match (100% for 2-term query)
        assert title_matches_query("PC Gamer Issue 400", "PC Gamer") is True
        # Magazine abbreviations like GQ, OK should now work
        assert title_matches_query("GQ Magazine UK", "GQ") is True

    def test_title_matches_query_no_significant_terms(self):
        """If all terms are too short (<2 chars), should pass (nothing to check)."""
        # Single-letter terms are ignored
        assert title_matches_query("Something Else", "a") is True
        assert title_matches_query("Something Else", "x y z") is True

    def test_filter_result_non_ia_always_passes(self):
        """Non-IA results should always pass regardless of content."""
        assert filter_result("Random Title", "newsnab", {}, "Something Else") is True
        assert filter_result("Random Title", "rss", {}, "Something Else") is True

    def test_filter_result_collection_filtered(self):
        """IA collection archives should be filtered out by default."""
        assert (
            filter_result(
                "My Archive Collection",
                "internet_archive",
                {"is_collection": True},
                "Test",
            )
            is False
        )

    def test_filter_result_collection_preserved_when_disabled(self):
        """IA collection archives should pass when filter_collections=False."""
        assert (
            filter_result(
                "My Archive Collection",
                "internet_archive",
                {"is_collection": True},
                "Archive",
                filter_collections=False,
            )
            is True
        )

    def test_filter_result_poor_title_filtered(self):
        """IA results with poor title match should be filtered out."""
        assert filter_result("Cooking Recipes Vol 5", "internet_archive", {}, "National Geographic") is False

    def test_filter_result_good_match_passes(self):
        """IA results with good title match should pass."""
        assert (
            filter_result(
                "National Geographic January 2024",
                "internet_archive",
                {},
                "National Geographic",
            )
            is True
        )

    def test_filter_result_no_query_skips_title_check(self):
        """When search_query is None, title-match check should be skipped."""
        assert filter_result("Completely Unrelated Title", "internet_archive", {}, None) is True


class TestCollectionQueryAutoAllow:
    """Test that title_matches_query auto-enables allow_collections when the query contains a collection word."""

    def test_query_contains_collection_word_true(self):
        """Queries with collection indicator words should be detected."""
        assert _query_contains_collection_word("Magazines Collection") is True
        assert _query_contains_collection_word("photography archive") is True
        assert _query_contains_collection_word("magazine pack") is True
        assert _query_contains_collection_word("PC Gamer bundle") is True

    def test_query_contains_collection_word_false(self):
        """Queries without collection indicator words should not be detected."""
        assert _query_contains_collection_word("National Geographic") is False
        assert _query_contains_collection_word("PC Gamer") is False
        assert _query_contains_collection_word("Wired Magazine") is False

    def test_query_contains_collection_word_case_insensitive(self):
        """Detection should be case-insensitive."""
        assert _query_contains_collection_word("Magazines COLLECTION") is True
        assert _query_contains_collection_word("Magazines Collection") is True
        assert _query_contains_collection_word("magazines collection") is True

    def test_collection_query_passes_collection_title(self):
        """A search for 'Magazines Collection' should accept NZB collection titles."""
        # This is the core bug fix: titles like "60 Magazines Collection PDF Set 332-xpost"
        # should NOT be rejected when the user's query contains "collection"
        assert (
            title_matches_query(
                "60 Magazines Collection PDF Set 332-xpost",
                "Magazines Collection",
            )
            is True
        )

    def test_non_collection_query_still_rejects_collection_title(self):
        """Without a collection word in the query, collection titles are still rejected."""
        assert (
            title_matches_query(
                "60 Magazines Collection PDF Set 332-xpost",
                "Wired",
            )
            is False
        )

    def test_explicit_allow_collections_still_works(self):
        """Passing allow_collections=True explicitly still overrides the filter."""
        assert (
            title_matches_query(
                "60 Magazines Collection PDF Set 332-xpost",
                "Magazines",
                allow_collections=True,
            )
            is True
        )

    def test_archive_in_query_allows_archive_title(self):
        """A query containing 'archive' auto-allows archive collection titles."""
        assert (
            title_matches_query(
                "National Geographic Complete Archive 1888-2024",
                "National Geographic archive",
            )
            is True
        )

    def test_pack_in_query_allows_pack_title(self):
        """A query containing 'pack' auto-allows pack collection titles."""
        assert (
            title_matches_query(
                "Wired Magazine Pack 2022-2024",
                "Wired pack",
            )
            is True
        )


class TestIaFilterInUiSearch:
    """Test that the IA filter is wired into the UI search filters module."""

    def test_filter_search_results_function_exists(self):
        """filters.py should expose filter_search_results function."""
        from web.routers.search.filters import filter_search_results

        assert callable(filter_search_results)

    def test_filter_search_results_preserves_collections(self):
        """UI filter should preserve IA collection archives and filter by title match."""
        from web.routers.search.filters import filter_search_results

        results = [
            # All providers are filtered by title match
            {
                "title": "National Geographic Traveler",
                "provider": "newsnab",
                "metadata": {},
            },
            {
                "title": "National Geographic Collection",
                "provider": "internet_archive",
                "metadata": {"is_collection": True},
            },
            {
                "title": "National Geographic Jan 2024",
                "provider": "internet_archive",
                "metadata": {},
            },
        ]
        filtered = filter_search_results(results, "National Geographic")
        assert len(filtered) == 3
        assert filtered[0]["title"] == "National Geographic Traveler"
        assert filtered[1]["title"] == "National Geographic Collection"
        assert filtered[2]["title"] == "National Geographic Jan 2024"

    def test_filter_search_results_filters_poor_matches(self):
        """UI filter should remove IA results that don't match the query."""
        from web.routers.search.filters import filter_search_results

        results = [
            {
                "title": "Unrelated Cookbook Vol 3",
                "provider": "internet_archive",
                "metadata": {},
            },
            {
                "title": "National Geographic Jan 2024",
                "provider": "internet_archive",
                "metadata": {},
            },
        ]
        filtered = filter_search_results(results, "National Geographic")
        assert len(filtered) == 1
        assert filtered[0]["title"] == "National Geographic Jan 2024"

    def test_filter_search_results_filters_all_providers_by_title_match(self):
        """All providers (not just IA) are filtered by title match."""
        from web.routers.search.filters import filter_search_results

        results = [
            # These don't match "National Geographic" so they get filtered
            {"title": "Completely Unrelated", "provider": "newsnab", "metadata": {}},
            {"title": "Also Unrelated", "provider": "rss", "metadata": {}},
            # This matches so it's kept
            {"title": "National Geographic UK", "provider": "newsnab", "metadata": {}},
        ]
        filtered = filter_search_results(results, "National Geographic")
        assert len(filtered) == 1
        assert filtered[0]["title"] == "National Geographic UK"

    def test_filter_search_results_imported_in_endpoints(self):
        """endpoints.py should import filter_search_results from filters."""
        import web.routers.search.endpoints as endpoints_mod
        from web.routers.search.filters import filter_search_results

        assert hasattr(endpoints_mod, "filter_search_results")


class TestIaFilterInAutoDownload:
    """Test that auto-download SearchService uses the shared IA filter."""

    def test_search_service_imports_filter_result(self):
        """SearchService should import filter_result from core.utils.result_filter."""
        import services.download.search_service as ss_mod

        assert hasattr(ss_mod, "filter_result")
        assert ss_mod.filter_result is filter_result


# =============================================================================
# Fix 4: Collection descriptor stripping from search queries
# =============================================================================


class TestCollectionDescriptorStripping:
    """Test that collection descriptor words are stripped from search queries."""

    def test_strips_collection_word(self):
        """'Hobby Magazine Collection' should become 'Hobby Magazine'."""
        from web.routers.search.providers import _strip_collection_descriptors

        assert _strip_collection_descriptors("Hobby Magazine Collection") == "Hobby Magazine"

    def test_strips_multiple_descriptors(self):
        """'National Geographic Complete Collection' should become 'National Geographic'."""
        from web.routers.search.providers import _strip_collection_descriptors

        assert _strip_collection_descriptors("National Geographic Complete Collection") == "National Geographic"

    def test_strips_pack_and_bundle(self):
        """Pack and Bundle descriptors should be stripped."""
        from web.routers.search.providers import _strip_collection_descriptors

        assert _strip_collection_descriptors("PC Gamer Pack 2024") == "PC Gamer 2024"
        assert _strip_collection_descriptors("Wired Magazine Bundle") == "Wired Magazine"

    def test_strips_archive_and_set(self):
        """Archive and Set descriptors should be stripped."""
        from web.routers.search.providers import _strip_collection_descriptors

        assert _strip_collection_descriptors("Time Magazine Archive") == "Time Magazine"
        assert _strip_collection_descriptors("Hobby Full Set") == "Hobby"

    def test_preserves_normal_queries(self):
        """Queries without collection descriptors should be unchanged."""
        from web.routers.search.providers import _strip_collection_descriptors

        assert _strip_collection_descriptors("PC Gamer") == "PC Gamer"
        assert _strip_collection_descriptors("National Geographic") == "National Geographic"
        assert _strip_collection_descriptors("Hobby") == "Hobby"

    def test_all_descriptor_words_preserves_query(self):
        """If all words are descriptors, preserve original to avoid empty search."""
        from web.routers.search.providers import _strip_collection_descriptors

        assert _strip_collection_descriptors("Complete Set") == "Complete Set"
        assert _strip_collection_descriptors("Full Collection") == "Full Collection"

    def test_case_insensitive(self):
        """Descriptor stripping should be case-insensitive."""
        from web.routers.search.providers import _strip_collection_descriptors

        assert _strip_collection_descriptors("Hobby COLLECTION") == "Hobby"
        assert _strip_collection_descriptors("Hobby Collection") == "Hobby"


# =============================================================================
# Fix 5: Newsnab category merge (user config + category map)
# =============================================================================


class TestNewsnabCategoryMerge:
    """Test that _search_xml_api merges mapped categories with user-configured categories."""

    def _make_provider(self, categories="6000,7000,8000"):
        """Create a NewsnabProvider with given user categories."""
        from providers.newsnab import NewsnabProvider

        config = {
            "api_url": "http://localhost:9696/1/api",
            "api_key": "test-key",
            "categories": categories,
        }
        return NewsnabProvider(config)

    @staticmethod
    def _empty_rss_response():
        """Create a mock response with empty RSS XML."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.content = b'<?xml version="1.0"?><rss><channel></channel></rss>'
        mock_response.text = '<?xml version="1.0"?><rss><channel></channel></rss>'
        return mock_response

    @patch("providers.newsnab.requests.get")
    def test_category_filter_uses_only_mapped_categories(self, mock_get):
        """When category filter is 'Magazines', only mapped categories should be used (not merged with user config)."""
        mock_get.return_value = self._empty_rss_response()

        provider = self._make_provider("6000,7000,8000")
        provider._search_xml_api("test", "Magazines")

        # Verify the request was made with only mapped categories
        call_args = mock_get.call_args
        cat_param = call_args[1]["params"]["cat"] if "params" in call_args[1] else call_args[0][1]["cat"]
        cat_set = set(cat_param.split(","))

        # Should include ONLY mapped categories (7010,8000,8010), NOT user-configured extras
        assert "7010" in cat_set, "Mapped category 7010 should be included"
        assert "8000" in cat_set, "Mapped category 8000 should be included"
        assert "8010" in cat_set, "Mapped category 8010 should be included"
        assert "6000" not in cat_set, "User-only category 6000 should NOT leak through filter"
        assert "7000" not in cat_set, "User-only category 7000 should NOT leak through filter"

    @patch("providers.newsnab.requests.get")
    def test_no_category_filter_uses_user_config(self, mock_get):
        """When no category filter, use user-configured categories as-is."""
        mock_get.return_value = self._empty_rss_response()

        provider = self._make_provider("6000,7000,8000")
        provider._search_xml_api("test", None)

        call_args = mock_get.call_args
        cat_param = call_args[1]["params"]["cat"] if "params" in call_args[1] else call_args[0][1]["cat"]
        assert cat_param == "6000,7000,8000"

    @patch("providers.newsnab.requests.get")
    def test_unknown_category_uses_user_config(self, mock_get):
        """When category filter doesn't exist in map, uses user config."""
        mock_get.return_value = self._empty_rss_response()

        provider = self._make_provider("6000,7000,8000")
        provider._search_xml_api("test", "NonExistentCategory")

        call_args = mock_get.call_args
        cat_param = call_args[1]["params"]["cat"] if "params" in call_args[1] else call_args[0][1]["cat"]
        assert cat_param == "6000,7000,8000"


# =============================================================================
# Fix 6: Provider timeout in UI search
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

        # Create a mock provider that raises TimeoutError
        slow_provider = MagicMock()
        slow_provider.__class__.__name__ = "SlowProvider"
        slow_provider.search.side_effect = FuturesTimeoutError("Search timed out")

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

        # Slow provider that raises timeout
        slow_provider = MagicMock()
        slow_provider.__class__.__name__ = "SlowProvider"
        slow_provider.search.side_effect = FuturesTimeoutError("Search timed out")

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
