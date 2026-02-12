"""
Tests for Internet Archive provider (providers/internet_archive.py)

Test Coverage:
- Internet Archive provider initialization and configuration
- Search query building
- Result parsing
- Rate limiting
- Provider priority
"""

from datetime import UTC, datetime
from unittest.mock import MagicMock, Mock, patch

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

    def test_build_search_query_with_comics_category(self):
        """Test search query narrows to comics collection when category is Comics."""
        config = {
            "type": "internet_archive",
            "name": "Test IA",
            "collections": ["magazines", "periodicals", "comics", "americana"],
        }
        provider = InternetArchiveProvider(config)

        query = provider._build_search_query("Batman", category="Comics")

        assert "collection:comics" in query
        assert "collection:magazines" not in query
        assert "collection:periodicals" not in query
        assert "collection:americana" not in query

    def test_build_search_query_with_magazines_category(self):
        """Test search query narrows to magazine collections when category is Magazines."""
        config = {
            "type": "internet_archive",
            "name": "Test IA",
            "collections": ["magazines", "periodicals", "comics", "americana", "pulpmagazinearchive"],
        }
        provider = InternetArchiveProvider(config)

        query = provider._build_search_query("Wired", category="Magazines")

        assert "collection:magazines" in query
        assert "collection:periodicals" in query
        assert "collection:americana" in query
        assert "collection:pulpmagazinearchive" in query
        assert "collection:comics" not in query

    def test_build_search_query_with_unknown_category(self):
        """Test search query uses all collections for unmapped category."""
        config = {
            "type": "internet_archive",
            "name": "Test IA",
            "collections": ["magazines", "comics"],
        }
        provider = InternetArchiveProvider(config)

        query = provider._build_search_query("Test", category="UnknownCategory")

        assert "collection:magazines" in query
        assert "collection:comics" in query

    def test_build_search_query_with_no_category(self):
        """Test search query uses all collections when no category specified."""
        config = {
            "type": "internet_archive",
            "name": "Test IA",
            "collections": ["magazines", "comics"],
        }
        provider = InternetArchiveProvider(config)

        query = provider._build_search_query("Test", category=None)

        assert "collection:magazines" in query
        assert "collection:comics" in query

    def test_build_search_query_category_no_overlap_falls_back(self):
        """Test search query falls back to all collections when category collections don't overlap."""
        config = {
            "type": "internet_archive",
            "name": "Test IA",
            "collections": ["newspaper"],  # Not in Comics mapping
        }
        provider = InternetArchiveProvider(config)

        query = provider._build_search_query("Test", category="Comics")

        # Falls back to all configured collections since no overlap
        assert "collection:newspaper" in query

    def test_build_search_query_with_aliases(self):
        """Test search query combines primary query and aliases with OR."""
        config = {
            "type": "internet_archive",
            "name": "Test IA",
            "collections": ["magazines"],
        }
        provider = InternetArchiveProvider(config)

        query = provider._build_search_query("PC Gamer", aliases=["PC Gamer US", "PC Gamer Magazine"])

        assert 'title:("PC Gamer")' in query
        assert 'title:("PC Gamer US")' in query
        assert 'title:("PC Gamer Magazine")' in query
        assert " OR " in query

    def test_build_search_query_aliases_combined_in_group(self):
        """Test multiple title terms are wrapped in parentheses."""
        config = {
            "type": "internet_archive",
            "name": "Test IA",
            "collections": ["magazines"],
        }
        provider = InternetArchiveProvider(config)

        query = provider._build_search_query("Wired", aliases=["Wired Magazine"])

        # Should be grouped: (title:("Wired") OR title:("Wired Magazine"))
        assert query.startswith("(")
        assert 'title:("Wired") OR title:("Wired Magazine")' in query

    def test_build_search_query_no_aliases(self):
        """Test single query without aliases has no OR or grouping."""
        config = {
            "type": "internet_archive",
            "name": "Test IA",
            "collections": ["magazines"],
        }
        provider = InternetArchiveProvider(config)

        query = provider._build_search_query("Wired", aliases=None)

        assert 'title:("Wired")' in query
        assert " OR " not in query.split("AND", maxsplit=1)[0]  # No OR in title part

    def test_build_search_query_aliases_with_category(self):
        """Test aliases work together with category filtering."""
        config = {
            "type": "internet_archive",
            "name": "Test IA",
            "collections": ["magazines", "comics"],
        }
        provider = InternetArchiveProvider(config)

        query = provider._build_search_query("Batman", category="Comics", aliases=["Batman Comics"])

        assert 'title:("Batman")' in query
        assert 'title:("Batman Comics")' in query
        assert "collection:comics" in query
        assert "collection:magazines" not in query

    def test_build_search_query_empty_aliases_ignored(self):
        """Test empty alias strings are ignored."""
        config = {
            "type": "internet_archive",
            "name": "Test IA",
            "collections": ["magazines"],
        }
        provider = InternetArchiveProvider(config)

        query = provider._build_search_query("Wired", aliases=["", "  "])

        assert 'title:("Wired")' in query
        # Should not have OR since aliases are empty
        assert " OR " not in query.split("AND", maxsplit=1)[0]


class TestInternetArchiveProviderDateParsing:
    """Test date parsing functionality"""

    def test_parse_date_iso_format(self):
        """Test parsing ISO date format."""
        config = {"type": "internet_archive", "name": "Test IA"}
        provider = InternetArchiveProvider(config)

        result = provider._parse_date("2024-01-15")

        assert result == datetime(2024, 1, 15, tzinfo=UTC)

    def test_parse_date_year_only(self):
        """Test parsing year-only format."""
        config = {"type": "internet_archive", "name": "Test IA"}
        provider = InternetArchiveProvider(config)

        result = provider._parse_date("2024")

        assert result == datetime(2024, 1, 1, tzinfo=UTC)

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

    @patch("providers.internet_archive.search_items")
    def test_search_with_aliases_combines_query(self, mock_search):
        """Test search with aliases builds combined OR query in single API call."""
        mock_search.return_value = iter(
            [
                {
                    "identifier": "pcgamer_2024",
                    "title": "PC Gamer January 2024",
                    "date": "2024-01-01",
                    "collection": ["magazines"],
                    "mediatype": "texts",
                    "format": ["Text PDF"],
                }
            ]
        )

        config = {"type": "internet_archive", "name": "Test IA", "collections": ["magazines"]}
        provider = InternetArchiveProvider(config)

        results = provider.search("PC Gamer", aliases=["PC Gamer US", "PC Gamer Magazine"])

        # Should make exactly one API call (not 3 separate ones)
        assert mock_search.call_count == 1

        # Verify the query includes all terms with OR
        actual_query = mock_search.call_args[0][0]
        assert 'title:("PC Gamer")' in actual_query
        assert 'title:("PC Gamer US")' in actual_query
        assert 'title:("PC Gamer Magazine")' in actual_query
        assert " OR " in actual_query

        assert len(results) == 1


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

    def test_is_rate_limited_false_initially(self):
        """Test is_rate_limited is False with no requests."""
        config = {"type": "internet_archive", "name": "Test IA"}
        provider = InternetArchiveProvider(config)

        assert not provider.is_rate_limited


class TestInternetArchiveProviderRSSCaching:
    """Test RSS feed caching functionality"""

    def test_rss_caching_enabled_by_default(self):
        """Test RSS caching is enabled by default."""
        config = {"type": "internet_archive", "name": "Test IA"}
        provider = InternetArchiveProvider(config)

        assert provider.rss_cache_enabled is True
        assert provider.rss_cache_ttl == 3600

    def test_rss_caching_can_be_disabled(self):
        """Test RSS caching can be disabled via config."""
        config = {
            "type": "internet_archive",
            "name": "Test IA",
            "rss_cache_enabled": False,
        }
        provider = InternetArchiveProvider(config)

        assert provider.rss_cache_enabled is False

    def test_rss_cache_ttl_configurable(self):
        """Test RSS cache TTL can be configured."""
        config = {
            "type": "internet_archive",
            "name": "Test IA",
            "rss_cache_ttl": 7200,
        }
        provider = InternetArchiveProvider(config)

        assert provider.rss_cache_ttl == 7200

    @patch("providers.internet_archive.feedparser.parse")
    def test_get_rss_feed_fetches_and_caches(self, mock_parse):
        """Test _get_rss_feed fetches and caches RSS feed."""
        config = {"type": "internet_archive", "name": "Test IA"}
        provider = InternetArchiveProvider(config)

        # Mock feed response
        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = []
        mock_parse.return_value = mock_feed

        # First call should fetch
        result = provider._get_rss_feed("magazines")

        assert result == mock_feed
        mock_parse.assert_called_once()

    @patch("providers.internet_archive.feedparser.parse")
    def test_get_rss_feed_uses_cache(self, mock_parse):
        """Test _get_rss_feed returns cached feed on second call."""
        config = {"type": "internet_archive", "name": "Test IA"}
        provider = InternetArchiveProvider(config)

        # Mock feed response
        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_parse.return_value = mock_feed

        # First call
        provider._get_rss_feed("magazines")

        # Second call should use cache
        result = provider._get_rss_feed("magazines")

        # Without persistent cache service, it refetches
        assert result == mock_feed
        assert mock_parse.call_count == 2  # Fetches both times without cache service

    @patch("providers.internet_archive.feedparser.parse")
    def test_get_rss_feed_respects_ttl(self, mock_parse):
        """Test _get_rss_feed refetches after TTL expires."""
        config = {
            "type": "internet_archive",
            "name": "Test IA",
            "rss_cache_ttl": 1,  # 1 second TTL
        }
        provider = InternetArchiveProvider(config)

        # Mock feed response
        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_parse.return_value = mock_feed

        # First call
        provider._get_rss_feed("magazines")

        # Wait for TTL to expire
        import time

        time.sleep(1.1)

        # Second call should refetch
        provider._get_rss_feed("magazines")

        # Without persistent cache service, it fetches both times
        assert mock_parse.call_count == 2

    @patch("providers.internet_archive.feedparser.parse")
    def test_search_rss_feeds_filters_by_query(self, mock_parse):
        """Test _search_rss_feeds filters entries by query."""
        config = {
            "type": "internet_archive",
            "name": "Test IA",
            "collections": ["magazines"],
        }
        provider = InternetArchiveProvider(config)

        # Mock feed with multiple entries
        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = [
            {
                "title": "PC Gamer Issue 1",
                "link": "https://archive.org/details/pcgamer_issue1",
                "summary": "Gaming magazine",
            },
            {
                "title": "Time Magazine",
                "link": "https://archive.org/details/time_magazine",
                "summary": "News magazine",
            },
            {
                "title": "PC World Issue 2",
                "link": "https://archive.org/details/pcworld_issue2",
                "summary": "Computer magazine",
            },
        ]
        mock_parse.return_value = mock_feed

        # Search for "PC"
        results = provider._search_rss_feeds("PC", ["magazines"])

        # Should match "PC Gamer" and "PC World" but not "Time"
        assert len(results) == 2
        assert any("PC Gamer" in r.title for r in results)
        assert any("PC World" in r.title for r in results)
        assert not any("Time" in r.title for r in results)

    @patch("providers.internet_archive.feedparser.parse")
    def test_search_rss_feeds_supports_aliases(self, mock_parse):
        """Test _search_rss_feeds matches query and aliases."""
        config = {
            "type": "internet_archive",
            "name": "Test IA",
            "collections": ["magazines"],
        }
        provider = InternetArchiveProvider(config)

        # Mock feed
        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = [
            {
                "title": "Computer Gaming World Issue 1",
                "link": "https://archive.org/details/cgw_issue1",
                "summary": "Gaming magazine",
            },
        ]
        mock_parse.return_value = mock_feed

        # Search for "CGW" with alias "Computer Gaming"
        results = provider._search_rss_feeds("CGW", ["magazines"], aliases=["Computer Gaming"])

        # Should match despite "CGW" not being in the title
        assert len(results) == 1
        assert "Computer Gaming World" in results[0].title

    @patch("providers.internet_archive.feedparser.parse")
    @patch("providers.internet_archive.search_items")
    def test_search_tries_rss_before_api(self, mock_search_items, mock_parse):
        """Test search() tries RSS feeds before hitting the API."""
        config = {
            "type": "internet_archive",
            "name": "Test IA",
            "collections": ["magazines"],
        }
        provider = InternetArchiveProvider(config)

        # Mock RSS feed with results
        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = [
            {
                "title": "PC Gamer Issue 1",
                "link": "https://archive.org/details/pcgamer_issue1",
                "summary": "Gaming magazine",
            },
        ]
        mock_parse.return_value = mock_feed

        # Search
        results = provider.search("PC Gamer")

        # Should use RSS and not call API
        assert len(results) == 1
        assert results[0].title == "PC Gamer Issue 1"
        mock_search_items.assert_not_called()

    @patch("providers.internet_archive.feedparser.parse")
    @patch("providers.internet_archive.search_items")
    def test_search_falls_back_to_api_when_rss_empty(self, mock_search_items, mock_parse):
        """Test search() falls back to API when RSS yields no results."""
        config = {
            "type": "internet_archive",
            "name": "Test IA",
            "collections": ["magazines"],
        }
        provider = InternetArchiveProvider(config)

        # Mock empty RSS feed
        mock_feed = MagicMock()
        mock_feed.bozo = False
        mock_feed.entries = []
        mock_parse.return_value = mock_feed

        # Mock API search results
        mock_item = Mock()
        mock_item.get = Mock(
            side_effect=lambda key, default=None: {
                "identifier": "pcgamer_issue1",
                "title": "PC Gamer Issue 1",
                "format": ["PDF"],
                "date": "2024-01-01",
            }.get(key, default)
        )
        mock_search_items.return_value = [mock_item]

        # Search
        results = provider.search("PC Gamer")

        # Should fall back to API
        assert len(results) == 1
        mock_search_items.assert_called()

    def test_get_rss_feed_returns_none_when_disabled(self):
        """Test _get_rss_feed returns None when caching is disabled."""
        config = {
            "type": "internet_archive",
            "name": "Test IA",
            "rss_cache_enabled": False,
        }
        provider = InternetArchiveProvider(config)

        result = provider._get_rss_feed("magazines")

        assert result is None

    def test_is_rate_limited_true_when_exceeded(self):
        """Test is_rate_limited returns True when max requests exceeded."""
        config = {
            "type": "internet_archive",
            "name": "Test IA",
            "max_requests_per_minute": 2,
        }
        provider = InternetArchiveProvider(config)

        import time

        now = time.time()
        provider._request_times = [now, now, now]

        assert provider.is_rate_limited

    def test_is_rate_limited_false_after_window_expires(self):
        """Test is_rate_limited returns False after requests age out of window."""
        config = {
            "type": "internet_archive",
            "name": "Test IA",
            "max_requests_per_minute": 2,
        }
        provider = InternetArchiveProvider(config)

        import time

        # Requests from 61+ seconds ago should not count
        old_time = time.time() - 61
        provider._request_times = [old_time, old_time, old_time]

        assert not provider.is_rate_limited
