"""Search parsing and error paths for the Internet Archive provider.

The archive library is mocked. Timeouts and empty payloads must come back as
empty results instead of escaping the provider.
"""

import time
from datetime import UTC, datetime
from unittest.mock import Mock, patch

import httpx

from providers.internet_archive import InternetArchiveProvider


def _provider(**overrides):
    config = {
        "type": "internet_archive",
        "name": "IA",
        "collections": ["magazines"],
        "request_delay": 0,
        "max_results": 50,
        "file_formats": ["PDF", "EPUB"],
    }
    config.update(overrides)
    return InternetArchiveProvider(config)


def _item(**overrides):
    payload = {
        "identifier": "natgeo-2024-01",
        "title": "National Geographic January 2024",
        "date": "2024-01-15",
        "creator": "National Geographic Society",
        "collection": ["magazines"],
        "mediatype": "texts",
        "format": ["Text PDF"],
    }
    payload.update(overrides)
    return payload


class TestSearchParsing:
    """Identifiers, titles, and skipped rows from an archive search page."""

    @patch("providers.internet_archive.search_items")
    def test_search_parses_titles_identifiers_and_dates(self, mock_search):
        mock_search.return_value = [
            _item(),
            _item(
                identifier="wired-collection",
                title=["Wired Magazine Collection", "unused second title"],
                date=["2020-06-01T00:00:00Z", "2020-07-01"],
                format="EPUB",
                item_count="4",
            ),
            _item(identifier="", title="Blank Identifier"),
            _item(identifier=None, title="Missing Identifier"),
            _item(identifier="scans-only", title="Scans Only", format=["DjVu"]),
        ]
        provider = _provider()

        results = provider.search("National Geographic")

        assert [(result.title, result.url) for result in results] == [
            ("National Geographic January 2024", "natgeo-2024-01"),
            ("Wired Magazine Collection", "wired-collection"),
        ]
        assert results[0].provider == "internet_archive"
        assert results[0].publication_date == datetime(2024, 1, 15, tzinfo=UTC)
        assert results[0].raw_metadata["identifier"] == "natgeo-2024-01"
        assert results[1].publication_date == datetime(2020, 6, 1, tzinfo=UTC)
        assert results[1].raw_metadata["identifier"] == "wired-collection"
        assert results[1].raw_metadata["is_collection"] is True
        assert results[1].raw_metadata["item_count"] == 4
        assert results[1].raw_metadata["available_formats"] == ["EPUB"]

    @patch("providers.internet_archive.search_items")
    def test_empty_title_list_uses_the_identifier(self, mock_search):
        mock_search.return_value = [_item(identifier="id-only", title=[], format=["PDF"])]
        provider = _provider(collections=[])

        results = provider.search("Id Only")

        assert len(results) == 1
        assert results[0].title == "id-only"
        assert results[0].url == "id-only"
        assert results[0].raw_metadata["identifier"] == "id-only"

    @patch("providers.internet_archive.search_items")
    def test_unparseable_row_is_skipped_and_neighbors_are_kept(self, mock_search):
        class Boom(dict):
            def get(self, key, default=None):
                raise ValueError("unparseable metadata")

        mock_search.return_value = [
            _item(identifier="before", title="Before"),
            Boom(identifier="bad", title="Bad"),
            _item(identifier="after", title="After", format=["EPUB"], date="2023"),
        ]
        provider = _provider()

        results = provider.search("Neighbors")

        assert [(result.title, result.url) for result in results] == [
            ("Before", "before"),
            ("After", "after"),
        ]
        assert results[1].publication_date == datetime(2023, 1, 1, tzinfo=UTC)

    @patch("providers.internet_archive.search_items")
    def test_empty_collection_page_falls_through_to_a_general_search(self, mock_search):
        mock_search.side_effect = [
            [],
            [_item(identifier="broad-hit", title="Broad Hit", format=["PDF"])],
        ]
        provider = _provider(collections=["magazines"])

        results = provider.search("Broad")

        assert [(result.title, result.url) for result in results] == [("Broad Hit", "broad-hit")]
        assert mock_search.call_count == 2
        collection_query = mock_search.call_args_list[0].args[0]
        general_query = mock_search.call_args_list[1].args[0]
        assert "collection:magazines" in collection_query
        assert "collection:" not in general_query
        assert 'title:("Broad")' in general_query


class TestSearchErrorPaths:
    """Empty payloads and transport failures stay inside the provider."""

    @patch("providers.internet_archive.search_items")
    def test_empty_iterator_returns_no_results(self, mock_search):
        mock_search.return_value = iter([])

        assert _provider(collections=[]).search("Nobody") == []

    @patch("providers.internet_archive.search_items")
    def test_empty_list_returns_no_results(self, mock_search):
        mock_search.return_value = []

        results = _provider(collections=[]).search("Nobody")

        assert results == []
        mock_search.assert_called_once()

    @patch("providers.internet_archive.search_items")
    def test_null_response_does_not_raise(self, mock_search):
        mock_search.return_value = None

        assert _provider(collections=[]).search("Nobody") == []

    @patch("providers.internet_archive.search_items")
    def test_timeout_does_not_raise(self, mock_search):
        mock_search.side_effect = httpx.TimeoutException("search timed out")

        assert _provider().search("Wired") == []

    @patch("providers.internet_archive.search_items")
    def test_timeout_on_the_general_search_does_not_raise(self, mock_search):
        mock_search.side_effect = [[], httpx.ReadTimeout("read timed out")]

        assert _provider(collections=["magazines"]).search("Wired") == []
        assert mock_search.call_count == 2

    @patch("providers.internet_archive.search_items")
    def test_timeout_while_iterating_results_does_not_raise(self, mock_search):
        def _page():
            yield _item(identifier="partial", title="Partial")
            raise httpx.ConnectTimeout("connect timed out")

        mock_search.return_value = _page()

        assert _provider().search("Partial") == []

    @patch("providers.internet_archive.search_items")
    def test_rate_limit_skips_the_archive_call(self, mock_search):
        provider = _provider(max_requests_per_minute=1)
        provider._request_times = [time.time()]

        assert provider.search("Wired") == []
        mock_search.assert_not_called()


class TestItemDownloadInfo:
    """Item metadata parsing and download-info failures."""

    @patch("providers.internet_archive.get_item")
    def test_download_info_uses_the_preferred_file_title_and_identifier(self, mock_get_item):
        item = Mock()
        item.item_metadata = {
            "files": [
                {"name": "cover.jpg", "format": "JPEG", "size": "12"},
                {"name": "issue.pdf", "format": "PDF", "size": "4096"},
                {"name": "broken.bin", "format": "PDF", "size": "nope"},
            ],
            "metadata": {"title": "January Issue"},
        }
        mock_get_item.return_value = item
        provider = _provider(request_delay=0)

        info = provider.get_item_download_info("natgeo-2024-01")

        assert info == {
            "identifier": "natgeo-2024-01",
            "download_url": "https://archive.org/download/natgeo-2024-01/issue.pdf",
            "file_name": "issue.pdf",
            "format": "PDF",
            "size": 4096,
            "title": "January Issue",
        }

    @patch("providers.internet_archive.get_item")
    def test_item_with_no_files_returns_none(self, mock_get_item):
        item = Mock()
        item.item_metadata = {"files": [], "metadata": {"title": "Empty"}}
        mock_get_item.return_value = item

        assert _provider().get_item_download_info("empty-item") is None

    @patch("providers.internet_archive.get_item")
    def test_item_timeout_does_not_raise(self, mock_get_item):
        mock_get_item.side_effect = httpx.TimeoutException("item timed out")

        assert _provider().get_item_download_info("slow-item") is None

    @patch("providers.internet_archive.search_items")
    def test_connection_success_and_timeout(self, mock_search):
        provider = _provider()
        mock_search.return_value = iter([{"identifier": "probe"}])

        success = provider.test_connection()

        assert success["success"] is True
        assert "successful" in success["message"]

        mock_search.side_effect = httpx.ConnectTimeout("connect timed out")

        failure = provider.test_connection()

        assert failure["success"] is False
        assert "connect timed out" in failure["message"]
