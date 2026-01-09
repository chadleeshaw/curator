"""
Tests for RSS feed provider (providers/rss.py)

Test Coverage:
- RSS provider initialization and configuration
- RSS feed parsing and search functionality
- Error handling for invalid feeds
- Date parsing from RSS entries
- Query filtering logic
- Result mapping to SearchResult objects
"""

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
from time import struct_time

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.bases import SearchResult
from providers.rss import RSSProvider


class TestRSSProviderInitialization:
    """Test RSS provider initialization and configuration"""

    def test_init_with_valid_config(self):
        """Test RSSProvider initializes with valid feed_url configuration."""
        config = {
            "type": "rss",
            "name": "Test RSS",
            "feed_url": "https://example.com/feed.xml",
            "enabled": True,
        }

        provider = RSSProvider(config)

        assert provider.feed_url == "https://example.com/feed.xml"
        assert provider.name == "Test RSS"
        assert provider.type == "rss"

    def test_init_missing_feed_url_raises_error(self):
        """Test RSSProvider raises ValueError when feed_url is missing."""
        config = {
            "type": "rss",
            "name": "Invalid RSS",
        }

        with pytest.raises(ValueError, match="RSS provider requires feed_url"):
            RSSProvider(config)

    def test_init_empty_feed_url_raises_error(self):
        """Test RSSProvider raises ValueError when feed_url is empty."""
        config = {
            "type": "rss",
            "name": "Invalid RSS",
            "feed_url": "",
        }

        with pytest.raises(ValueError, match="RSS provider requires feed_url"):
            RSSProvider(config)

    def test_inherits_from_search_provider(self):
        """Test RSSProvider properly inherits from SearchProvider base class."""
        config = {
            "type": "rss",
            "feed_url": "https://example.com/feed.xml",
        }

        provider = RSSProvider(config)

        assert hasattr(provider, "search")
        assert hasattr(provider, "get_provider_info")
        assert provider.config == config


class TestRSSProviderSearch:
    """Test RSS feed search functionality"""

    @patch("providers.rss.feedparser.parse")
    def test_search_returns_matching_results(self, mock_parse):
        """Test search returns entries matching the query."""
        # Arrange
        config = {
            "type": "rss",
            "feed_url": "https://example.com/feed.xml",
        }
        provider = RSSProvider(config)

        # Create mock entries as objects with attributes (like feedparser returns)
        entry1 = Mock()
        entry1.get = lambda key, default="": {
            "title": "National Geographic January 2024",
            "link": "https://example.com/nat-geo-jan-2024",
            "summary": "Amazing wildlife photos",
            "id": "ng-jan-2024",
        }.get(key, default)
        entry1.published_parsed = struct_time((2024, 1, 15, 10, 30, 0, 0, 0, 0))

        entry2 = Mock()
        entry2.get = lambda key, default="": {
            "title": "National Geographic February 2024",
            "link": "https://example.com/nat-geo-feb-2024",
            "summary": "Ocean exploration",
            "id": "ng-feb-2024",
        }.get(key, default)
        entry2.published_parsed = struct_time((2024, 2, 15, 10, 30, 0, 0, 0, 0))

        entry3 = Mock()
        entry3.get = lambda key, default="": {
            "title": "Time Magazine January 2024",
            "link": "https://example.com/time-jan-2024",
            "summary": "World news",
            "id": "time-jan-2024",
        }.get(key, default)
        delattr(entry3, "published_parsed")  # No published_parsed attribute

        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = [entry1, entry2, entry3]
        mock_parse.return_value = mock_feed

        # Act
        results = provider.search("National Geographic")

        # Assert
        assert len(results) == 2
        assert all(isinstance(r, SearchResult) for r in results)
        assert results[0].title == "National Geographic January 2024"
        assert results[1].title == "National Geographic February 2024"
        assert "national geographic" in results[0].title.lower()

    @patch("providers.rss.feedparser.parse")
    def test_search_case_insensitive(self, mock_parse):
        """Test search is case-insensitive when matching queries."""
        config = {"type": "rss", "feed_url": "https://example.com/feed.xml"}
        provider = RSSProvider(config)

        entry = Mock()
        entry.get = lambda key, default="": {
            "title": "NATIONAL GEOGRAPHIC January 2024",
            "link": "https://example.com/nat-geo",
        }.get(key, default)
        delattr(entry, "published_parsed")

        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = [entry]
        mock_parse.return_value = mock_feed

        results = provider.search("national geographic")

        assert len(results) == 1
        assert results[0].title == "NATIONAL GEOGRAPHIC January 2024"

    @patch("providers.rss.feedparser.parse")
    def test_search_returns_empty_list_when_no_matches(self, mock_parse):
        """Test search returns empty list when no entries match query."""
        config = {"type": "rss", "feed_url": "https://example.com/feed.xml"}
        provider = RSSProvider(config)

        entry = Mock()
        entry.get = lambda key, default="": {
            "title": "Time Magazine January 2024",
            "link": "https://example.com/time",
        }.get(key, default)
        delattr(entry, "published_parsed")

        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = [entry]
        mock_parse.return_value = mock_feed

        results = provider.search("National Geographic")

        assert len(results) == 0
        assert results == []

    @patch("providers.rss.feedparser.parse")
    def test_search_extracts_publication_date(self, mock_parse):
        """Test search extracts publication_date from published_parsed field."""
        config = {"type": "rss", "feed_url": "https://example.com/feed.xml"}
        provider = RSSProvider(config)

        entry = Mock()
        entry.get = lambda key, default="": {
            "title": "Magazine January 2024",
            "link": "https://example.com/mag",
        }.get(key, default)
        entry.published_parsed = struct_time((2024, 1, 15, 14, 30, 45, 0, 0, 0))

        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = [entry]
        mock_parse.return_value = mock_feed

        results = provider.search("Magazine")

        assert len(results) == 1
        assert results[0].publication_date == datetime(2024, 1, 15, 14, 30, 45)

    @patch("providers.rss.feedparser.parse")
    def test_search_handles_missing_publication_date(self, mock_parse):
        """Test search handles entries without published_parsed gracefully."""
        config = {"type": "rss", "feed_url": "https://example.com/feed.xml"}
        provider = RSSProvider(config)

        entry = Mock()
        entry.get = lambda key, default="": {
            "title": "Magazine January 2024",
            "link": "https://example.com/mag",
        }.get(key, default)
        delattr(entry, "published_parsed")  # No published_parsed attribute

        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = [entry]
        mock_parse.return_value = mock_feed

        results = provider.search("Magazine")

        assert len(results) == 1
        assert results[0].publication_date is None

    @patch("providers.rss.feedparser.parse")
    def test_search_includes_raw_metadata(self, mock_parse):
        """Test search includes summary and guid in raw_metadata."""
        config = {"type": "rss", "feed_url": "https://example.com/feed.xml"}
        provider = RSSProvider(config)

        entry = Mock()
        entry.get = lambda key, default="": {
            "title": "Test Magazine",
            "link": "https://example.com/test",
            "summary": "A great magazine issue",
            "id": "test-123",
        }.get(key, default)
        delattr(entry, "published_parsed")

        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = [entry]
        mock_parse.return_value = mock_feed

        results = provider.search("Magazine")

        assert len(results) == 1
        assert results[0].raw_metadata["summary"] == "A great magazine issue"
        assert results[0].raw_metadata["guid"] == "test-123"

    @patch("providers.rss.feedparser.parse")
    def test_search_handles_missing_optional_fields(self, mock_parse):
        """Test search handles missing optional fields in RSS entries."""
        config = {"type": "rss", "feed_url": "https://example.com/feed.xml"}
        provider = RSSProvider(config)

        entry = Mock()
        entry.get = lambda key, default="": {
            "title": "Test Magazine",
        }.get(key, default)
        delattr(entry, "published_parsed")

        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = [entry]
        mock_parse.return_value = mock_feed

        results = provider.search("Magazine")

        assert len(results) == 1
        assert results[0].url == ""
        assert results[0].raw_metadata["summary"] == ""
        assert results[0].raw_metadata["guid"] == ""

    @patch("providers.rss.feedparser.parse")
    def test_search_sets_provider_type(self, mock_parse):
        """Test search results include correct provider type."""
        config = {"type": "rss", "feed_url": "https://example.com/feed.xml"}
        provider = RSSProvider(config)

        entry = Mock()
        entry.get = lambda key, default="": {
            "title": "Test Magazine",
            "link": "https://example.com/test",
        }.get(key, default)
        delattr(entry, "published_parsed")

        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = [entry]
        mock_parse.return_value = mock_feed

        results = provider.search("Magazine")

        assert len(results) == 1
        assert results[0].provider == "rss"


class TestRSSProviderErrorHandling:
    """Test RSS provider error handling"""

    @patch("providers.rss.feedparser.parse")
    def test_search_handles_bozo_feed(self, mock_parse):
        """Test search handles malformed RSS feeds (bozo bit set)."""
        config = {"type": "rss", "feed_url": "https://example.com/feed.xml"}
        provider = RSSProvider(config)

        entry = Mock()
        entry.get = lambda key, default="": {
            "title": "Test Magazine",
            "link": "https://example.com/test",
        }.get(key, default)
        delattr(entry, "published_parsed")

        mock_feed = MagicMock()
        mock_feed.bozo = True
        mock_feed.bozo_exception = Exception("Malformed XML")
        mock_feed.entries = [entry]
        mock_parse.return_value = mock_feed

        # Should still attempt to process entries despite bozo warning
        results = provider.search("Magazine")

        assert len(results) == 1
        assert results[0].title == "Test Magazine"

    @patch("providers.rss.feedparser.parse")
    def test_search_handles_feedparser_exception(self, mock_parse):
        """Test search handles exceptions from feedparser gracefully."""
        config = {"type": "rss", "feed_url": "https://example.com/feed.xml"}
        provider = RSSProvider(config)

        mock_parse.side_effect = Exception("Network error")

        results = provider.search("Magazine")

        assert results == []

    @patch("providers.rss.feedparser.parse")
    def test_search_handles_invalid_date_format(self, mock_parse):
        """Test search handles invalid published_parsed date gracefully."""
        config = {"type": "rss", "feed_url": "https://example.com/feed.xml"}
        provider = RSSProvider(config)

        entry = Mock()
        entry.get = lambda key, default="": {
            "title": "Test Magazine",
            "link": "https://example.com/test",
            "summary": "",
            "id": "",
        }.get(key, default)

        # Make published_parsed None (falsy but attribute exists)
        entry.published_parsed = None

        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = [entry]
        mock_parse.return_value = mock_feed

        results = provider.search("Magazine")

        # Should still return result but with no publication date
        assert len(results) == 1
        assert results[0].publication_date is None

    @patch("providers.rss.feedparser.parse")
    def test_search_handles_empty_feed(self, mock_parse):
        """Test search handles empty RSS feed (no entries)."""
        config = {"type": "rss", "feed_url": "https://example.com/feed.xml"}
        provider = RSSProvider(config)

        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = []
        mock_parse.return_value = mock_feed

        results = provider.search("Magazine")

        assert results == []

    @patch("providers.rss.feedparser.parse")
    def test_search_calls_feedparser_with_feed_url(self, mock_parse):
        """Test search calls feedparser.parse with configured feed URL."""
        config = {
            "type": "rss",
            "feed_url": "https://magazines.example.com/rss/all.xml",
        }
        provider = RSSProvider(config)

        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = []
        mock_parse.return_value = mock_feed

        provider.search("Test")

        mock_parse.assert_called_once_with("https://magazines.example.com/rss/all.xml")


class TestRSSProviderIntegration:
    """Integration tests for RSS provider"""

    @patch("providers.rss.feedparser.parse")
    def test_search_multiple_matching_entries(self, mock_parse):
        """Test searching feed with multiple matching entries."""
        config = {"type": "rss", "feed_url": "https://example.com/feed.xml"}
        provider = RSSProvider(config)

        entry1 = Mock()
        entry1.get = lambda key, default="": {
            "title": "Wired Magazine January 2024",
            "link": "https://example.com/wired-jan",
            "summary": "Tech news",
            "id": "wired-jan",
        }.get(key, default)
        entry1.published_parsed = struct_time((2024, 1, 1, 0, 0, 0, 0, 0, 0))

        entry2 = Mock()
        entry2.get = lambda key, default="": {
            "title": "Wired Magazine February 2024",
            "link": "https://example.com/wired-feb",
            "summary": "AI developments",
            "id": "wired-feb",
        }.get(key, default)
        entry2.published_parsed = struct_time((2024, 2, 1, 0, 0, 0, 0, 0, 0))

        entry3 = Mock()
        entry3.get = lambda key, default="": {
            "title": "Wired Magazine March 2024",
            "link": "https://example.com/wired-mar",
            "summary": "Future tech",
            "id": "wired-mar",
        }.get(key, default)
        entry3.published_parsed = struct_time((2024, 3, 1, 0, 0, 0, 0, 0, 0))

        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = [entry1, entry2, entry3]
        mock_parse.return_value = mock_feed

        results = provider.search("Wired")

        assert len(results) == 3
        assert all(r.provider == "rss" for r in results)
        assert results[0].title == "Wired Magazine January 2024"
        assert results[1].title == "Wired Magazine February 2024"
        assert results[2].title == "Wired Magazine March 2024"
        assert results[0].publication_date.month == 1
        assert results[1].publication_date.month == 2
        assert results[2].publication_date.month == 3

    @patch("providers.rss.feedparser.parse")
    def test_provider_info_matches_config(self, mock_parse):
        """Test get_provider_info returns correct metadata."""
        config = {
            "type": "rss",
            "name": "Magazine RSS Feed",
            "feed_url": "https://example.com/feed.xml",
            "enabled": True,
        }
        provider = RSSProvider(config)

        info = provider.get_provider_info()

        assert info["type"] == "rss"
        assert info["name"] == "Magazine RSS Feed"
        assert info["enabled"] is True
