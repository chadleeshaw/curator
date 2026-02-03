"""
Tests for Internet Archive provider (providers/internet_archive.py)

Test Coverage:
- Internet Archive provider initialization and configuration
- Search query building
- Result parsing
- Rate limiting
- Provider priority
"""

from datetime import datetime
from unittest.mock import MagicMock, Mock, patch

import pytest

# Path setup handled by conftest.py

from core.interfaces import SearchResult
from providers.internet_archive import InternetArchiveProvider


class TestInternetArchiveProviderInitialization:
    """Test Internet Archive provider initialization and configuration"""

    def test_init_with_valid_config(self):
        """Test InternetArchiveProvider initializes with valid configuration."""
        config = {
            "type": "internet_archive",
            "name": "Test IA",
            "enabled": True,
            "priority": 10,
        }

        provider = InternetArchiveProvider(config)

        assert provider.name == "Test IA"
        assert provider.type == "internet_archive"
        assert provider.priority == 10

    def test_init_with_default_values(self):
        """Test InternetArchiveProvider uses default values when not specified."""
        config = {
            "type": "internet_archive",
            "name": "Test IA",
        }

        provider = InternetArchiveProvider(config)

        assert provider.mediatype == "texts"
        assert provider.max_results == 100
        assert provider.priority == 10
        assert len(provider.collections) > 0
        assert "PDF" in provider.preferred_formats

    def test_init_with_custom_collections(self):
        """Test InternetArchiveProvider with custom collections."""
        config = {
            "type": "internet_archive",
            "name": "Test IA",
            "collections": ["magazines", "comics"],
        }

        provider = InternetArchiveProvider(config)

        assert provider.collections == ["magazines", "comics"]

    def test_init_with_custom_formats(self):
        """Test InternetArchiveProvider with custom file formats."""
        config = {
            "type": "internet_archive",
            "name": "Test IA",
            "file_formats": ["EPUB", "PDF"],
        }

        provider = InternetArchiveProvider(config)

        assert provider.preferred_formats == ["EPUB", "PDF"]

    def test_inherits_from_search_provider(self):
        """Test InternetArchiveProvider properly inherits from SearchProvider base class."""
        config = {
            "type": "internet_archive",
            "name": "Test IA",
        }

        provider = InternetArchiveProvider(config)

        assert hasattr(provider, "search")
        assert hasattr(provider, "get_provider_info")
        assert provider.config == config


class TestInternetArchiveProviderSearchQuery:
    """Test search query building"""

    def test_build_search_query_basic(self):
        """Test basic search query building."""
        config = {
            "type": "internet_archive",
            "name": "Test IA",
            "collections": ["magazines"],
        }
        provider = InternetArchiveProvider(config)

        query = provider._build_search_query("Wired Magazine")

        assert 'title:("Wired Magazine")' in query
        assert "mediatype:texts" in query
        assert "collection:magazines" in query

    def test_build_search_query_multiple_collections(self):
        """Test search query with multiple collections."""
        config = {
            "type": "internet_archive",
            "name": "Test IA",
            "collections": ["magazines", "periodicals"],
        }
        provider = InternetArchiveProvider(config)

        query = provider._build_search_query("Test")

        assert "collection:magazines" in query
        assert "collection:periodicals" in query


class TestInternetArchiveProviderDateParsing:
    """Test date parsing functionality"""

    def test_parse_date_iso_format(self):
        """Test parsing ISO date format."""
        config = {"type": "internet_archive", "name": "Test IA"}
        provider = InternetArchiveProvider(config)

        result = provider._parse_date("2024-01-15")

        assert result == datetime(2024, 1, 15)

    def test_parse_date_year_only(self):
        """Test parsing year-only format."""
        config = {"type": "internet_archive", "name": "Test IA"}
        provider = InternetArchiveProvider(config)

        result = provider._parse_date("2024")

        assert result == datetime(2024, 1, 1)

    def test_parse_date_invalid(self):
        """Test parsing invalid date returns None."""
        config = {"type": "internet_archive", "name": "Test IA"}
        provider = InternetArchiveProvider(config)

        result = provider._parse_date("invalid")

        assert result is None

    def test_parse_date_none(self):
        """Test parsing None returns None."""
        config = {"type": "internet_archive", "name": "Test IA"}
        provider = InternetArchiveProvider(config)

        result = provider._parse_date(None)

        assert result is None


class TestInternetArchiveProviderSearch:
    """Test search functionality"""

    @patch("providers.internet_archive.search_items")
    def test_search_returns_results(self, mock_search):
        """Test search returns properly formatted results."""
        # Mock search results - must include 'format' field for items to pass filter
        mock_search.return_value = iter(
            [
                {
                    "identifier": "wired_2024_01",
                    "title": "Wired Magazine January 2024",
                    "date": "2024-01-01",
                    "creator": "Conde Nast",
                    "description": "Technology magazine",
                    "collection": ["magazines"],
                    "mediatype": "texts",
                    "format": ["Text PDF", "JPEG Thumb"],  # Required for format filtering
                }
            ]
        )

        config = {"type": "internet_archive", "name": "Test IA"}
        provider = InternetArchiveProvider(config)

        results = provider.search("Wired")

        assert len(results) == 1
        assert results[0].title == "Wired Magazine January 2024"
        assert results[0].url == "wired_2024_01"  # Identifier stored as URL
        assert results[0].provider == "internet_archive"

    @patch("providers.internet_archive.search_items")
    def test_search_handles_empty_results(self, mock_search):
        """Test search handles empty results gracefully."""
        mock_search.return_value = iter([])

        config = {"type": "internet_archive", "name": "Test IA"}
        provider = InternetArchiveProvider(config)

        results = provider.search("NonexistentMagazine")

        assert results == []

    @patch("providers.internet_archive.search_items")
    def test_search_handles_exception(self, mock_search):
        """Test search handles exceptions gracefully."""
        mock_search.side_effect = Exception("Network error")

        config = {"type": "internet_archive", "name": "Test IA"}
        provider = InternetArchiveProvider(config)

        results = provider.search("Wired")

        assert results == []


class TestInternetArchiveProviderRateLimiting:
    """Test rate limiting functionality"""

    def test_rate_limit_not_triggered_initially(self):
        """Test rate limiting not triggered with no requests."""
        config = {"type": "internet_archive", "name": "Test IA"}
        provider = InternetArchiveProvider(config)

        assert not provider._check_rate_limit()

    def test_rate_limit_triggered_when_exceeded(self):
        """Test rate limiting triggered when max requests exceeded."""
        config = {
            "type": "internet_archive",
            "name": "Test IA",
            "max_requests_per_minute": 2,
        }
        provider = InternetArchiveProvider(config)

        # Simulate exceeding rate limit
        import time

        now = time.time()
        provider._request_times = [now, now, now]

        assert provider._check_rate_limit()
