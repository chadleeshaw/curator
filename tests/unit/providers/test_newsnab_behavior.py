"""Behavior tests for Newsnab search, XML parsing, and rate-limit backoff.

HTTP is mocked. Request-delay sleeps are patched so the suite does not wait.
"""

import time
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from core.constants.providers import (
    NEWSNAB_DEFAULT_RATE_LIMIT_WAIT,
    NEWSNAB_REQUEST_TIMEOUT,
    SECONDS_PER_DAY,
    SECONDS_PER_HOUR,
)
from core.interfaces import SearchResult
from core.parsers import utc_now
from providers.newsnab import NewsnabProvider

NEWZNAB_NS = "http://www.newznab.com/DTD/2010/feeds/attributes/"


def _make_provider(**overrides):
    config = {
        "type": "newsnab",
        "name": "Test Indexer",
        "api_url": "http://indexer.test/1",
        "api_key": "test-key-123",
        "categories": "7010",
        "rss_categories": "7010,7030",
        "request_delay_seconds": 0,
        "max_requests_per_hour": 100,
        "search_limit": 25,
        "rss_max_results": 10,
    }
    config.update(overrides)
    return NewsnabProvider(config)


def _response(status, content=b"", headers=None):
    request = httpx.Request("GET", "http://indexer.test/1/api")
    return httpx.Response(status, content=content, headers=headers or {}, request=request)


def _item_xml(
    *,
    title="National Geographic January 2025",
    include_title=True,
    link="https://indexer.example/details/1",
    enclosure_url="https://indexer.example/get/1.nzb",
    enclosure_length=None,
    pub_date="Mon, 20 Jan 2025 12:34:56 +0000",
    size="54321",
    files="3",
    category="7010",
    guid=None,
    indexer="NZBGeek",
):
    parts = []
    if include_title:
        parts.append(f"<title>{title}</title>")
    if link is not None:
        parts.append(f"<link>{link}</link>")
    if enclosure_url is not None or enclosure_length is not None:
        length = f' length="{enclosure_length}"' if enclosure_length is not None else ""
        url = enclosure_url or ""
        parts.append(f'<enclosure url="{url}"{length} type="application/x-nzb"/>')
    if pub_date is not None:
        parts.append(f"<pubDate>{pub_date}</pubDate>")
    if indexer is not None:
        parts.append(f"<indexer>{indexer}</indexer>")
    if guid:
        parts.append(f"<guid>{guid}</guid>")
    if category is not None:
        parts.append(f'<newznab:attr name="category" value="{category}"/>')
    if size is not None:
        parts.append(f'<newznab:attr name="size" value="{size}"/>')
    if files is not None:
        parts.append(f'<newznab:attr name="files" value="{files}"/>')
    return "<item>" + "".join(parts) + "</item>"


def _rss_xml(*items, error=None):
    error_xml = ""
    if error is not None:
        code, description = error
        error_xml = f'<error code="{code}" description="{description}"/>'
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<rss xmlns:newznab="{NEWZNAB_NS}"><channel>{error_xml}{"".join(items)}</channel></rss>'
    )
    return xml.encode()


def _install_httpx(monkeypatch, responder):
    calls = []

    def _get(url, params=None, timeout=None):
        call = {"url": url, "params": dict(params or {}), "timeout": timeout}
        calls.append(call)
        result = responder(call) if callable(responder) else responder
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr("providers.newsnab.httpx.get", _get)
    return calls


def _assert_wait(provider, seconds, tolerance=3):
    remaining = (provider._rate_limit_until - utc_now()).total_seconds()
    assert abs(remaining - seconds) < tolerance
    assert provider.is_rate_limited is True


class TestNewsnabSearchParsing:
    """search() parses Newznab RSS items and query parameters."""

    def test_requires_api_key(self):
        with pytest.raises(ValueError, match="api_key"):
            NewsnabProvider({"type": "newsnab", "api_url": "http://indexer.test"})

    def test_search_parses_titles_urls_dates_and_metadata(self, monkeypatch):
        xml = _rss_xml(
            _item_xml(guid="ignored-on-search"),
            _item_xml(
                title="Link Only Issue",
                link="https://indexer.example/details/2",
                enclosure_url=None,
                pub_date="2025-03-01T08:00:00+0000",
                size=None,
                files=None,
                category=None,
                indexer="LinkIndexer",
            ),
            _item_xml(
                title="Enclosure Length Issue",
                enclosure_url="https://indexer.example/get/3.nzb",
                enclosure_length=999,
                pub_date="2025-04-02 09:30:00",
                size="nope",
                files=None,
                category=None,
                indexer=None,
            ),
            _item_xml(
                title="No Date Issue",
                enclosure_url="https://indexer.example/get/4.nzb",
                pub_date=None,
                size=None,
                files=None,
                category=None,
                indexer=None,
            ),
            _item_xml(
                title="Bad Date Issue",
                enclosure_url="https://indexer.example/get/5.nzb",
                pub_date="yesterday",
                size=None,
                files=None,
                category=None,
                indexer=None,
            ),
            _item_xml(title="", enclosure_url="https://indexer.example/get/skipped.nzb"),
        )
        calls = _install_httpx(monkeypatch, lambda _call: _response(200, xml))
        provider = _make_provider()

        results = provider.search("National Geographic", category="Magazines")

        assert calls[0]["url"] == "http://indexer.test/1/api"
        assert calls[0]["timeout"] == NEWSNAB_REQUEST_TIMEOUT
        assert calls[0]["params"]["apikey"] == "test-key-123"
        assert calls[0]["params"]["t"] == "search"
        assert calls[0]["params"]["q"] == "National Geographic"
        assert calls[0]["params"]["cat"] == "7010,8000,8010"
        assert calls[0]["params"]["limit"] == 25
        assert [result.title for result in results] == [
            "National Geographic January 2025",
            "Link Only Issue",
            "Enclosure Length Issue",
            "No Date Issue",
            "Bad Date Issue",
        ]
        first = results[0]
        assert first.url == "https://indexer.example/get/1.nzb"
        assert first.provider == "newsnab"
        assert first.publication_date == datetime(2025, 1, 20, 12, 34, 56, tzinfo=UTC)
        assert first.raw_metadata["upload_date"] == first.publication_date.isoformat()
        assert first.raw_metadata["category"] == "7010"
        assert first.raw_metadata["size"] == 54321
        assert first.raw_metadata["files"] == 3
        assert first.raw_metadata["indexer"] == "NZBGeek"
        assert "guid" not in first.raw_metadata
        assert results[1].url == "https://indexer.example/details/2"
        assert results[1].publication_date == datetime(2025, 3, 1, 8, 0, tzinfo=UTC)
        assert "size" not in results[1].raw_metadata
        assert results[2].publication_date == datetime(2025, 4, 2, 9, 30, tzinfo=UTC)
        assert results[2].raw_metadata["size"] == 999
        assert results[3].publication_date is None
        assert "upload_date" not in results[3].raw_metadata
        assert results[4].publication_date is None

    def test_unknown_category_uses_configured_categories(self, monkeypatch):
        calls = _install_httpx(monkeypatch, lambda _call: _response(200, _rss_xml()))
        provider = _make_provider(categories="7010,7030")

        assert provider.search("Wired", category="NotACategory") == []
        assert calls[0]["params"]["cat"] == "7010,7030"

    def test_empty_channel_returns_no_results(self, monkeypatch):
        _install_httpx(monkeypatch, lambda _call: _response(200, _rss_xml()))
        provider = _make_provider()

        assert provider.search("Wired") == []

    def test_invalid_xml_returns_no_results(self, monkeypatch):
        _install_httpx(monkeypatch, lambda _call: _response(200, b"<rss><channel>"))
        provider = _make_provider()

        assert provider.search("Wired") == []
        assert provider.is_rate_limited is False

    def test_alias_results_are_deduped_by_url(self, monkeypatch):
        def responder(call):
            query = call["params"]["q"]
            if query == "Wired":
                return _response(200, _rss_xml(_item_xml(title="Wired Jan", enclosure_url="https://nzb/1")))
            if query == "Wire Magazine":
                return _response(
                    200,
                    _rss_xml(
                        _item_xml(title="Duplicate", enclosure_url="https://nzb/1"),
                        _item_xml(title="Alias Hit", enclosure_url="https://nzb/2"),
                    ),
                )
            raise AssertionError(query)

        calls = _install_httpx(monkeypatch, responder)
        provider = _make_provider()

        results = provider.search("Wired", aliases=["", "Wired", "Wire Magazine"])

        assert [call["params"]["q"] for call in calls] == ["Wired", "Wire Magazine"]
        assert [(result.title, result.url) for result in results] == [
            ("Wired Jan", "https://nzb/1"),
            ("Alias Hit", "https://nzb/2"),
        ]

    def test_alias_errors_do_not_abort_remaining_aliases(self, monkeypatch):
        provider = _make_provider()

        def fake_search(query, category=None):
            if query == "bad":
                raise RuntimeError("alias failed")
            return [SearchResult(title=query, url=f"https://nzb/{query}", provider="newsnab")]

        monkeypatch.setattr(provider, "_search_xml_api", fake_search)

        results = provider.search("Main", aliases=["bad", "Next"])

        assert [result.title for result in results] == ["Main", "Next"]

    def test_unexpected_search_error_returns_no_results(self, monkeypatch):
        provider = _make_provider()

        def explode(query, category=None):
            raise RuntimeError("parser exploded")

        monkeypatch.setattr(provider, "_search_xml_api", explode)

        assert provider.search("Wired") == []

    def test_request_delay_is_patched_and_does_not_block(self, monkeypatch):
        slept = []
        monkeypatch.setattr("providers.newsnab.time.sleep", lambda seconds: slept.append(seconds))
        xml = _rss_xml(_item_xml(title="Delayed Hit", enclosure_url="https://nzb/delayed"))
        _install_httpx(monkeypatch, lambda _call: _response(200, xml))
        provider = _make_provider(request_delay_seconds=5)
        provider._request_times.append(time.time())

        started = time.monotonic()
        results = provider.search("Wired")
        elapsed = time.monotonic() - started

        assert elapsed < 1
        assert len(slept) == 1
        assert 4 <= slept[0] <= 5
        assert [result.title for result in results] == ["Delayed Hit"]

    def test_alias_request_delay_is_patched(self, monkeypatch):
        slept = []
        monkeypatch.setattr("providers.newsnab.time.sleep", lambda seconds: slept.append(seconds))
        _install_httpx(monkeypatch, lambda _call: _response(200, _rss_xml()))
        provider = _make_provider(request_delay_seconds=3)

        started = time.monotonic()
        provider.search("Wired", aliases=["Alias"])
        elapsed = time.monotonic() - started

        assert elapsed < 1
        assert len(slept) == 1
        assert 2 <= slept[0] <= 3


class TestNewsnabHttpErrors:
    """Transport and HTTP failures return an empty result list."""

    def test_connect_error_returns_no_results(self, monkeypatch):
        def explode(_call):
            raise httpx.ConnectError("refused")

        _install_httpx(monkeypatch, explode)
        provider = _make_provider()

        assert provider.search("Wired") == []
        assert provider._rate_limit_until is None

    def test_timeout_returns_no_results(self, monkeypatch):
        def explode(_call):
            raise httpx.TimeoutException("timed out")

        _install_httpx(monkeypatch, explode)
        provider = _make_provider()

        assert provider.search("Wired") == []
        assert provider.is_rate_limited is False

    def test_http_500_does_not_start_cooldown(self, monkeypatch):
        _install_httpx(monkeypatch, lambda _call: _response(500, b"Internal Server Error"))
        provider = _make_provider()

        assert provider.search("Wired") == []
        assert provider._rate_limit_until is None

    def test_http_error_body_sets_rate_limit_backoff(self, monkeypatch):
        body = b"Too Many Requests. Retry after 15 seconds"
        _install_httpx(monkeypatch, lambda _call: _response(503, body))
        provider = _make_provider()

        assert provider.search("Wired") == []
        _assert_wait(provider, 15)
        assert "503" in provider._rate_limit_reason


class TestNewsnabRateLimitBackoff:
    """Cooldown is recorded from provider responses and skips further calls."""

    @pytest.mark.parametrize(
        ("retry_after", "expected"),
        [
            ("90", 90),
            (None, NEWSNAB_DEFAULT_RATE_LIMIT_WAIT),
            ("nope", NEWSNAB_DEFAULT_RATE_LIMIT_WAIT),
            # Retry-After: 0 is treated as missing because `if not wait_time` rejects 0.
            ("0", NEWSNAB_DEFAULT_RATE_LIMIT_WAIT),
        ],
    )
    def test_http_429_sets_backoff_and_skips_the_next_search(self, monkeypatch, retry_after, expected):
        headers = {} if retry_after is None else {"Retry-After": retry_after}
        calls = _install_httpx(monkeypatch, lambda _call: _response(429, b"slow down", headers))
        provider = _make_provider()

        assert provider.search("Wired") == []
        assert provider.search("Again") == []

        assert len(calls) == 1
        _assert_wait(provider, expected)
        assert provider._rate_limit_reason == "HTTP 429 Too Many Requests"

    @pytest.mark.parametrize(
        ("description", "seconds"),
        [
            ("Request limit reached. Please wait 45 seconds", 45),
            ("Please wait 2 minutes", 120),
            ("Please wait 3 hours", 3 * SECONDS_PER_HOUR),
            ("Daily limit exceeded", SECONDS_PER_DAY),
            ("Hourly limit exceeded", SECONDS_PER_HOUR),
        ],
    )
    def test_wrapped_xml_error_sets_backoff(self, monkeypatch, description, seconds):
        xml = _rss_xml(error=("429", description))
        _install_httpx(monkeypatch, lambda _call: _response(200, xml))
        provider = _make_provider()

        assert provider.search("Wired") == []
        _assert_wait(provider, seconds)
        assert description in provider._rate_limit_reason

    def test_non_rate_limit_xml_error_returns_empty_without_cooldown(self, monkeypatch):
        xml = _rss_xml(error=("200", "Unknown function"))
        _install_httpx(monkeypatch, lambda _call: _response(200, xml))
        provider = _make_provider()

        assert provider.search("Wired") == []
        assert provider._rate_limit_until is None

    def test_root_error_element_is_not_treated_as_rate_limit(self, monkeypatch):
        """Standard Newznab errors use <error> as the document root.

        `_check_xml_error` looks up `.//error`, which does not match the root
        element. A root rate-limit error is therefore an empty result and does
        not start a cooldown.
        """
        xml = (
            b'<?xml version="1.0" encoding="UTF-8"?>'
            b'<error code="429" description="Request limit reached. Please wait 10 seconds"/>'
        )
        _install_httpx(monkeypatch, lambda _call: _response(200, xml))
        provider = _make_provider()

        assert provider.search("Wired") == []
        assert provider._rate_limit_until is None
        assert provider.is_rate_limited is False

    def test_active_cooldown_skips_http_and_sleep(self, monkeypatch):
        slept = []
        monkeypatch.setattr("providers.newsnab.time.sleep", lambda seconds: slept.append(seconds))

        def fail_if_called(_call):
            raise AssertionError("HTTP should not be called during cooldown")

        calls = _install_httpx(monkeypatch, fail_if_called)
        provider = _make_provider(request_delay_seconds=30)
        provider._request_times.append(time.time())
        provider._rate_limit_until = utc_now() + timedelta(seconds=100)
        provider._rate_limit_reason = "already limited"

        assert provider.search("Wired") == []
        assert provider.search("") == []
        assert calls == []
        assert slept == []

    def test_expired_cooldown_allows_the_next_search(self, monkeypatch):
        xml = _rss_xml(_item_xml(title="After Cooldown", enclosure_url="https://nzb/after"))
        calls = _install_httpx(monkeypatch, lambda _call: _response(200, xml))
        provider = _make_provider()
        provider._rate_limit_until = utc_now() - timedelta(seconds=5)
        provider._rate_limit_reason = "old limit"
        provider._rate_limit_logged = True

        results = provider.search("Wired")

        assert len(calls) == 1
        assert [result.title for result in results] == ["After Cooldown"]
        assert provider._rate_limit_until is None
        assert provider._rate_limit_reason is None

    def test_self_imposed_limit_stops_alias_searches(self, monkeypatch):
        calls = _install_httpx(monkeypatch, lambda _call: _response(200, _rss_xml()))
        provider = _make_provider(max_requests_per_hour=2)

        results = provider.search("Main", aliases=["Alias 1", "Alias 2", "Alias 3"])

        assert results == []
        assert [call["params"]["q"] for call in calls] == ["Main", "Alias 1"]
        assert provider.is_rate_limited is True
        assert "Self-limit" in provider._rate_limit_reason
        _assert_wait(provider, SECONDS_PER_HOUR, tolerance=5)

    def test_self_imposed_limit_skips_before_any_request(self, monkeypatch):
        calls = _install_httpx(monkeypatch, lambda _call: _response(200, _rss_xml()))
        provider = _make_provider(max_requests_per_hour=2)
        now = time.time()
        provider._request_times = [now, now - 1]

        assert provider.search("Wired") == []
        assert calls == []
        assert provider.is_rate_limited is True


class TestNewsnabRssMode:
    """Empty queries use RSS mode, including the error-202 fallback."""

    def test_blank_query_parses_guid_and_omits_q(self, monkeypatch):
        xml = _rss_xml(
            _item_xml(
                title="Latest Magazine",
                enclosure_url="https://nzb/latest",
                guid="guid-latest",
                pub_date="Mon, 20 Jan 2025 12:34:56 +0000",
            )
        )
        calls = _install_httpx(monkeypatch, lambda _call: _response(200, xml))
        provider = _make_provider()

        results = provider.search("   ")

        assert "q" not in calls[0]["params"]
        assert calls[0]["params"]["t"] == "search"
        assert calls[0]["params"]["cat"] == "7010,7030"
        assert calls[0]["params"]["limit"] == provider.rss_max_results
        assert len(results) == 1
        assert results[0].title == "Latest Magazine"
        assert results[0].url == "https://nzb/latest"
        assert results[0].publication_date == datetime(2025, 1, 20, 12, 34, 56, tzinfo=UTC)
        assert results[0].raw_metadata["guid"] == "guid-latest"

    def test_rss_category_filter_overrides_rss_categories(self, monkeypatch):
        calls = _install_httpx(monkeypatch, lambda _call: _response(200, _rss_xml()))
        provider = _make_provider()

        assert provider.search("", category="Comics") == []
        assert calls[0]["params"]["cat"] == "7030,8000,8010"
        assert "q" not in calls[0]["params"]

    def test_rss_connect_error_returns_no_results(self, monkeypatch):
        def explode(_call):
            raise httpx.ConnectError("refused")

        _install_httpx(monkeypatch, explode)
        provider = _make_provider()

        assert provider.search("") == []

    def test_xml_error_202_falls_back_to_broad_search(self, monkeypatch):
        def responder(call):
            if "q" not in call["params"]:
                return _response(200, _rss_xml(error=("202", "No such function")))
            query = call["params"]["q"]
            return _response(
                200,
                _rss_xml(_item_xml(title=query, enclosure_url=f"https://nzb/{query}", guid=f"g-{query}")),
            )

        calls = _install_httpx(monkeypatch, responder)
        provider = _make_provider()
        year = str(datetime.now().year)

        results = provider.search("")

        assert [call["params"].get("q") for call in calls] == [None, "magazine", year]
        assert [result.title for result in results] == ["magazine", year]
        assert all("guid" not in result.raw_metadata for result in results)

    def test_http_400_code_202_falls_back_to_broad_search(self, monkeypatch):
        def responder(call):
            if "q" not in call["params"]:
                return _response(400, b'<?xml version="1.0"?><error code="202" description="No such function"/>')
            query = call["params"]["q"]
            return _response(200, _rss_xml(_item_xml(title=f"hit {query}", enclosure_url=f"https://nzb/{query}")))

        calls = _install_httpx(monkeypatch, responder)
        provider = _make_provider()

        results = provider.search("")

        assert calls[0]["params"].get("q") is None
        assert [call["params"].get("q") for call in calls[1:]] == ["magazine", str(datetime.now().year)]
        assert [result.title for result in results] == ["hit magazine", f"hit {datetime.now().year}"]
