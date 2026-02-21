#!/usr/bin/env python3
"""
Test suite for Torznab Search Provider
"""

import xml.etree.ElementTree as ET
from unittest.mock import Mock, patch

import pytest
import requests

# Path setup handled by conftest.py

from providers.torznab import (
    TORZNAB_DEFAULT_CATEGORIES,
    TORZNAB_DEFAULT_SEARCH_LIMIT,
    TorznabProvider,
    _attr,
    _int_attr,
    _parse_date,
)

# ---------------------------------------------------------------------------
# Helpers: minimal Torznab XML fixtures
# ---------------------------------------------------------------------------

_TORZNAB_NS = "http://torznab.com/schemas/2015/feed"
_NEWZNAB_NS = "http://www.newznab.com/DTD/2010/feeds/attributes/"

CAPS_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<caps>
  <server version="1.0" title="Prowlarr" />
  <searching>
    <search available="yes" supportedParams="q" />
  </searching>
</caps>
"""

SEARCH_XML_MAGNET = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
  xmlns:torznab="http://torznab.com/schemas/2015/feed">
  <channel>
    <title>Prowlarr</title>
    <item>
      <title>National Geographic 2024-01</title>
      <pubDate>Mon, 01 Jan 2024 00:00:00 +0000</pubDate>
      <torznab:attr name="magneturl" value="magnet:?xt=urn:btih:abc123&amp;dn=Nat+Geo" />
      <torznab:attr name="seeders" value="10" />
      <torznab:attr name="leechers" value="2" />
      <torznab:attr name="size" value="52428800" />
    </item>
    <item>
      <title>National Geographic 2024-02</title>
      <pubDate>Thu, 01 Feb 2024 00:00:00 +0000</pubDate>
      <torznab:attr name="magneturl" value="magnet:?xt=urn:btih:def456&amp;dn=Nat+Geo+Feb" />
      <torznab:attr name="seeders" value="5" />
      <torznab:attr name="leechers" value="1" />
      <torznab:attr name="size" value="48000000" />
    </item>
  </channel>
</rss>
"""

SEARCH_XML_ENCLOSURE = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
  xmlns:torznab="http://torznab.com/schemas/2015/feed">
  <channel>
    <item>
      <title>Some Magazine 2024-03</title>
      <enclosure url="https://example.com/torrent/mag.torrent" type="application/x-bittorrent" />
      <torznab:attr name="seeders" value="3" />
    </item>
  </channel>
</rss>
"""

SEARCH_XML_LINK_FALLBACK = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
  xmlns:torznab="http://torznab.com/schemas/2015/feed">
  <channel>
    <item>
      <title>Fallback Magazine 2024-04</title>
      <link>https://example.com/download/fallback.torrent</link>
    </item>
  </channel>
</rss>
"""

SEARCH_XML_NO_URL = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
  xmlns:torznab="http://torznab.com/schemas/2015/feed">
  <channel>
    <item>
      <title>Bad Item No URL</title>
    </item>
  </channel>
</rss>
"""

SEARCH_XML_NO_TITLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
  xmlns:torznab="http://torznab.com/schemas/2015/feed">
  <channel>
    <item>
      <torznab:attr name="magneturl" value="magnet:?xt=urn:btih:orphan" />
    </item>
  </channel>
</rss>
"""

SEARCH_XML_EMPTY = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel></channel>
</rss>
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def config():
    return {
        "name": "My Torznab",
        "type": "torznab",
        "api_url": "http://localhost:9696",
        "api_key": "testkey123",
        "categories": "7000,7010",
    }


@pytest.fixture
def provider(config):
    return TorznabProvider(config)


def _mock_response(content: bytes, status_code: int = 200) -> Mock:
    resp = Mock()
    resp.content = content
    resp.status_code = status_code
    resp.raise_for_status = Mock()
    return resp


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


def test_initialization(config):
    """Test TorznabProvider initializes with values from config."""
    p = TorznabProvider(config)

    assert p.api_url == "http://localhost:9696"
    assert p.api_key == "testkey123"
    assert p.categories == "7000,7010"
    assert p.search_limit == TORZNAB_DEFAULT_SEARCH_LIMIT


def test_initialization_defaults():
    """Test TorznabProvider uses default categories and limits when not specified."""
    p = TorznabProvider({"api_url": "http://localhost:9696"})

    assert p.categories == TORZNAB_DEFAULT_CATEGORIES
    assert p.search_limit == TORZNAB_DEFAULT_SEARCH_LIMIT
    assert p.api_key == ""


def test_initialization_strips_api_suffix():
    """Test that /api and /api/v1 suffixes are stripped from api_url."""
    p1 = TorznabProvider({"api_url": "http://localhost:9696/api"})
    p2 = TorznabProvider({"api_url": "http://localhost:9696/api/v1"})
    p3 = TorznabProvider({"api_url": "http://localhost:9696/1/api"})

    assert p1.api_url == "http://localhost:9696"
    assert p2.api_url == "http://localhost:9696"
    # Only trailing /api suffix stripped
    assert p3.api_url == "http://localhost:9696/1"


def test_initialization_raises_without_api_url():
    """Test that TorznabProvider raises ValueError when api_url is missing."""
    with pytest.raises(ValueError, match="api_url"):
        TorznabProvider({})


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


def test_search_returns_results(provider):
    """Test that search returns parsed results from XML response."""
    with patch(
        "providers.torznab.requests.get", return_value=_mock_response(SEARCH_XML_MAGNET)
    ):
        results = provider.search("National Geographic")

    assert len(results) == 2
    assert results[0].title == "National Geographic 2024-01"
    assert results[1].title == "National Geographic 2024-02"


def test_search_result_has_magnet_url(provider):
    """Test that search results contain the magnet URL."""
    with patch(
        "providers.torznab.requests.get", return_value=_mock_response(SEARCH_XML_MAGNET)
    ):
        results = provider.search("National Geographic")

    assert results[0].url == "magnet:?xt=urn:btih:abc123&dn=Nat+Geo"


def test_search_result_metadata(provider):
    """Test that search results include seeders, leechers, and size metadata."""
    with patch(
        "providers.torznab.requests.get", return_value=_mock_response(SEARCH_XML_MAGNET)
    ):
        results = provider.search("National Geographic")

    meta = results[0].raw_metadata
    assert meta["seeders"] == 10
    assert meta["leechers"] == 2
    assert meta["size"] == 52428800
    assert meta["is_torrent"] is True


def test_search_falls_back_to_enclosure_url(provider):
    """Test that search uses enclosure URL when no magnet link is present."""
    with patch(
        "providers.torznab.requests.get",
        return_value=_mock_response(SEARCH_XML_ENCLOSURE),
    ):
        results = provider.search("Some Magazine")

    assert len(results) == 1
    assert results[0].url == "https://example.com/torrent/mag.torrent"


def test_search_falls_back_to_link_element(provider):
    """Test that search uses <link> element as last resort for URL."""
    with patch(
        "providers.torznab.requests.get",
        return_value=_mock_response(SEARCH_XML_LINK_FALLBACK),
    ):
        results = provider.search("Fallback Magazine")

    assert len(results) == 1
    assert results[0].url == "https://example.com/download/fallback.torrent"


def test_search_skips_items_without_url(provider):
    """Test that items with no downloadable URL are skipped."""
    with patch(
        "providers.torznab.requests.get", return_value=_mock_response(SEARCH_XML_NO_URL)
    ):
        results = provider.search("Bad Item")

    assert results == []


def test_search_skips_items_without_title(provider):
    """Test that items without a title element are skipped."""
    with patch(
        "providers.torznab.requests.get",
        return_value=_mock_response(SEARCH_XML_NO_TITLE),
    ):
        results = provider.search("orphan")

    assert results == []


def test_search_empty_channel(provider):
    """Test that an empty channel returns an empty list."""
    with patch(
        "providers.torznab.requests.get", return_value=_mock_response(SEARCH_XML_EMPTY)
    ):
        results = provider.search("nothing")

    assert results == []


def test_search_with_aliases_deduplicates(provider):
    """Test that alias searches merge results and deduplicate by URL."""
    with patch(
        "providers.torznab.requests.get", return_value=_mock_response(SEARCH_XML_MAGNET)
    ):
        results = provider.search("National Geographic", aliases=["Nat Geo"])

    # Both searches return the same URLs — results should be deduplicated
    urls = [r.url for r in results]
    assert len(urls) == len(set(urls))


def test_search_includes_api_key_in_request(provider):
    """Test that search request includes apikey parameter."""
    with patch(
        "providers.torznab.requests.get", return_value=_mock_response(SEARCH_XML_EMPTY)
    ) as mock_get:
        provider.search("test")

    call_kwargs = mock_get.call_args[1]
    assert call_kwargs["params"]["apikey"] == "testkey123"


def test_search_omits_api_key_when_empty():
    """Test that apikey is omitted from request when not configured."""
    p = TorznabProvider({"api_url": "http://localhost:9696"})
    with patch(
        "providers.torznab.requests.get", return_value=_mock_response(SEARCH_XML_EMPTY)
    ) as mock_get:
        p.search("test")

    call_kwargs = mock_get.call_args[1]
    assert "apikey" not in call_kwargs["params"]


def test_search_returns_empty_on_connection_error(provider):
    """Test that search returns [] on ConnectionError."""
    with patch(
        "providers.torznab.requests.get",
        side_effect=requests.exceptions.ConnectionError("down"),
    ):
        results = provider.search("test")

    assert results == []


def test_search_returns_empty_on_timeout(provider):
    """Test that search returns [] on Timeout."""
    with patch(
        "providers.torznab.requests.get", side_effect=requests.exceptions.Timeout
    ):
        results = provider.search("test")

    assert results == []


def test_search_returns_empty_on_bad_xml(provider):
    """Test that search returns [] when XML response is malformed."""
    with patch(
        "providers.torznab.requests.get", return_value=_mock_response(b"not xml at all")
    ):
        results = provider.search("test")

    assert results == []


# ---------------------------------------------------------------------------
# test_connection
# ---------------------------------------------------------------------------


def test_test_connection_success(provider):
    """Test that test_connection returns success with indexer title."""
    with patch("providers.torznab.requests.get", return_value=_mock_response(CAPS_XML)):
        result = provider.test_connection()

    assert result["success"] is True
    assert "Prowlarr" in result["message"]


def test_test_connection_includes_api_key(provider):
    """Test that test_connection sends the apikey parameter."""
    with patch(
        "providers.torznab.requests.get", return_value=_mock_response(CAPS_XML)
    ) as mock_get:
        provider.test_connection()

    call_kwargs = mock_get.call_args[1]
    assert call_kwargs["params"]["apikey"] == "testkey123"
    assert call_kwargs["params"]["t"] == "caps"


def test_test_connection_no_server_element(provider):
    """Test that test_connection works even if <server> element is absent."""
    xml_no_server = b"""<?xml version="1.0"?><caps></caps>"""
    with patch(
        "providers.torznab.requests.get", return_value=_mock_response(xml_no_server)
    ):
        result = provider.test_connection()

    assert result["success"] is True
    assert "Torznab" in result["message"]


def test_test_connection_timeout(provider):
    """Test that test_connection handles Timeout gracefully."""
    with patch(
        "providers.torznab.requests.get", side_effect=requests.exceptions.Timeout
    ):
        result = provider.test_connection()

    assert result["success"] is False
    assert "timeout" in result["message"].lower()


def test_test_connection_connection_error(provider):
    """Test that test_connection handles ConnectionError gracefully."""
    with patch(
        "providers.torznab.requests.get",
        side_effect=requests.exceptions.ConnectionError("down"),
    ):
        result = provider.test_connection()

    assert result["success"] is False
    assert (
        "failed" in result["message"].lower()
        or "connection" in result["message"].lower()
    )


# ---------------------------------------------------------------------------
# get_provider_info
# ---------------------------------------------------------------------------


def test_get_provider_info_includes_api_url(provider):
    """Test that get_provider_info includes the api_url field."""
    info = provider.get_provider_info()
    assert info["api_url"] == "http://localhost:9696"


# ---------------------------------------------------------------------------
# Helper functions: _parse_date, _attr, _int_attr
# ---------------------------------------------------------------------------


def test_parse_date_valid():
    """Test _parse_date parses standard RSS date format."""
    result = _parse_date("Mon, 01 Jan 2024 00:00:00 +0000")
    assert result is not None
    assert result.year == 2024
    assert result.month == 1


def test_parse_date_none():
    """Test _parse_date returns None for None input."""
    assert _parse_date(None) is None


def test_parse_date_unparseable():
    """Test _parse_date returns None for unrecognized format."""
    assert _parse_date("not a date") is None


def _make_item_with_attr(name: str, value: str, ns: str = _TORZNAB_NS) -> ET.Element:
    """Build a minimal RSS item with a single namespace attribute."""
    item = ET.Element("item")
    attr_el = ET.SubElement(item, f"{{{ns}}}attr")
    attr_el.set("name", name)
    attr_el.set("value", value)
    return item


def test_attr_finds_torznab_namespace():
    """Test _attr extracts value from torznab namespace."""
    item = _make_item_with_attr("seeders", "42", _TORZNAB_NS)
    assert _attr(item, "seeders") == "42"


def test_attr_finds_newznab_namespace():
    """Test _attr falls back to newznab namespace."""
    item = _make_item_with_attr("seeders", "7", _NEWZNAB_NS)
    assert _attr(item, "seeders") == "7"


def test_attr_returns_none_when_missing():
    """Test _attr returns None when the attribute is not present."""
    item = ET.Element("item")
    assert _attr(item, "nonexistent") is None


def test_int_attr_converts_to_int():
    """Test _int_attr returns integer value."""
    item = _make_item_with_attr("seeders", "15")
    assert _int_attr(item, "seeders") == 15


def test_int_attr_returns_none_for_non_numeric():
    """Test _int_attr returns None for non-numeric values."""
    item = _make_item_with_attr("seeders", "lots")
    assert _int_attr(item, "seeders") is None


def test_int_attr_returns_none_when_missing():
    """Test _int_attr returns None when attribute is absent."""
    item = ET.Element("item")
    assert _int_attr(item, "seeders") is None
