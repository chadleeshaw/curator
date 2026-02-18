"""
Tests for low-severity code quality fixes.

Validates that the following fixes work correctly:
1. submission_service.update_submission_for_retry uses 'last_error' (not 'error_message')
2. build_search_response uses utc_now() instead of deprecated datetime.utcnow()
3. Newsnab RSS fallback uses dynamic year generation
4. _extract_edition_variant renamed to public extract_edition_variant
5. Queue processor removed phantom 'skipped_count'
6. Deduplication service uses utc_now() instead of datetime.now()
7. Inline __import__ replaced with proper imports in cache models
8. DRY: download_manager uses _get_active_download_count and _get_download_category helpers
9. ThreadPoolExecutor reused across providers instead of per-iteration creation
"""

import sys
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))


class TestSubmissionServiceLastError:
    """Verify update_submission_for_retry sets last_error (not error_message)."""

    def test_update_submission_for_retry_clears_last_error(self):
        """The method should set submission.last_error = None, not error_message."""
        from services.download.submission_service import SubmissionService

        mock_submission = MagicMock()
        mock_submission.status = MagicMock()
        mock_submission.attempt_count = 1
        mock_session = MagicMock()

        SubmissionService.update_submission_for_retry(mock_submission, mock_session)

        # Should set last_error (the actual column name), NOT error_message
        assert mock_submission.last_error is None

    def test_update_submission_for_retry_increments_attempt(self):
        """Attempt count should increment on retry."""
        from services.download.submission_service import SubmissionService

        mock_submission = MagicMock()
        mock_submission.attempt_count = 2
        mock_session = MagicMock()

        SubmissionService.update_submission_for_retry(mock_submission, mock_session)

        assert mock_submission.attempt_count == 3


class TestBuildSearchResponseUtcNow:
    """Verify build_search_response no longer uses deprecated datetime.utcnow()."""

    def test_no_datetime_utcnow_import(self):
        """library.py should import utc_now from core.parsers."""
        import web.routers.search.library as lib_module

        assert hasattr(lib_module, "utc_now"), "utc_now should be imported in library.py"

    def test_cache_age_calculation_with_results(self):
        """Cache age should be calculated correctly when cached results exist."""
        from web.routers.search.library import build_search_response
        from core.parsers import utc_now

        mock_cached = MagicMock()
        mock_cached.created_at = utc_now() - timedelta(days=5)

        result = build_search_response(
            query="test",
            library_matches=[{"title": "Test", "status": "library"}],
            provider_results=[],
            cached_results=[mock_cached],
            provider_errors=[],
        )

        assert result["found"] is True
        assert result["cache_age_days"] == 5

    def test_cache_age_none_when_no_cache(self):
        """Cache age should be None when no cached results."""
        from web.routers.search.library import build_search_response

        result = build_search_response(
            query="test",
            library_matches=[],
            provider_results=[],
            cached_results=[],
            provider_errors=[],
        )

        assert result["cache_age_days"] is None


class TestNewsnabDynamicYears:
    """Verify RSS fallback uses dynamic current/previous year."""

    def test_search_terms_contain_current_year(self):
        """RSS fallback should include current year dynamically."""
        from providers.newsnab import NewsnabProvider

        config = {
            "type": "newsnab",
            "name": "Test",
            "api_url": "http://test/api",
            "api_key": "testkey",
        }
        provider = NewsnabProvider(config)

        # Access the method to check its source
        import inspect

        source = inspect.getsource(provider._search_xml_api_rss_fallback)  # pylint: disable=protected-access

        # Should NOT contain hardcoded years
        assert '"2024"' not in source
        assert '"2025"' not in source
        # Should use dynamic year generation
        assert "current_year" in source or "datetime" in source


class TestPublicExtractEditionVariant:
    """Verify _extract_edition_variant is now public (extract_edition_variant)."""

    def test_method_is_public(self):
        """TitleMatcher should have public extract_edition_variant method."""
        from core.parsers import TitleMatcher

        matcher = TitleMatcher(threshold=80)
        assert hasattr(matcher, "extract_edition_variant")

    def test_public_method_works(self):
        """Public method should work identically to the old private one."""
        from core.parsers import TitleMatcher

        matcher = TitleMatcher(threshold=80)

        assert matcher.extract_edition_variant("PC Gamer US") == "us"
        assert matcher.extract_edition_variant("National Geographic Kids") == "kids"
        assert matcher.extract_edition_variant("National Geographic") is None

    def test_callers_use_public_method(self):
        """External callers should use the public method name."""
        import inspect

        from web.routers.search import filters

        source = inspect.getsource(filters.filter_edition_variants)
        assert "_extract_edition_variant" not in source
        assert "extract_edition_variant" in source


class TestQueueProcessorNoSkippedCount:
    """Verify queue_processor.process_queue no longer returns phantom 'skipped' key."""

    def test_return_dict_has_no_skipped_key(self):
        """process_queue return dict should not include the always-zero 'skipped' field."""
        from services.download.queue_processor import QueueProcessor

        mock_client = MagicMock()
        mock_client.config = {"default_category": "test"}
        processor = QueueProcessor(mock_client, max_downloads=10)

        mock_session = MagicMock()
        # Simulate at capacity (active >= max)
        mock_session.query.return_value.filter.return_value.count.return_value = 10

        result = processor.process_queue(mock_session)

        assert "skipped" not in result
        assert "checked" in result
        assert "submitted" in result
        assert "errors" in result


class TestDeduplicationServiceUtcNow:
    """Verify DeduplicationService uses utc_now() instead of datetime.now()."""

    def test_no_datetime_now_in_source(self):
        """Source code should not contain datetime.now()."""
        import inspect
        from services.download.deduplication_service import DeduplicationService

        source = inspect.getsource(DeduplicationService)
        assert "datetime.now()" not in source

    def test_uses_utc_now(self):
        """Source code should use utc_now() for cutoff calculation."""
        import inspect
        from services.download.deduplication_service import DeduplicationService

        source = inspect.getsource(DeduplicationService)
        assert "utc_now()" in source
        # Should strip timezone for SQLite compatibility
        assert "replace(tzinfo=None)" in source


class TestProperSqlalchemyImports:
    """Verify inline __import__ patterns replaced with proper imports."""

    def test_cache_model_uses_proper_import(self):
        """models/cache.py should import UniqueConstraint normally."""
        import inspect
        import models.cache as cache_module

        source = inspect.getsource(cache_module)
        assert "__import__" not in source
        assert "UniqueConstraint" in source

    def test_provider_cache_uses_proper_import(self):
        """provider_cache.py should import text normally."""
        import inspect
        import services.cache.provider_cache as pc_module

        source = inspect.getsource(pc_module)
        assert "__import__" not in source
        assert "from sqlalchemy" in source


class TestDownloadManagerDRY:
    """Verify download_manager uses helper methods instead of inline duplications."""

    def test_no_unused_imports(self):
        """download_manager.py should not import unused datetime or FileCategorizer."""
        import inspect
        import services.download_manager as dm_module

        source = inspect.getsource(dm_module)
        # Should not import datetime directly (uses utc_now instead)
        assert "from datetime import datetime" not in source
        # Should not import FileCategorizer (was unused)
        assert "FileCategorizer" not in source

    def test_submit_from_discovered_uses_helper(self):
        """submit_from_discovered_issue should use _get_active_download_count helper."""
        import inspect
        from services.download_manager import DownloadManager

        source = inspect.getsource(DownloadManager.submit_from_discovered_issue)
        assert "_get_active_download_count" in source

    def test_retry_uses_get_download_category(self):
        """retry_submission should use _get_download_category helper."""
        import inspect
        from services.download_manager import DownloadManager

        source = inspect.getsource(DownloadManager.retry_submission)
        assert "_get_download_category" in source


class TestThreadPoolExecutorReuse:
    """Verify ThreadPoolExecutor is created once per search, not per provider."""

    def test_executor_outside_loop(self):
        """Provider search should create executor outside the provider loop."""
        import inspect
        from web.routers.search.providers import fetch_from_providers

        source = inspect.getsource(fetch_from_providers)

        # The pattern should be: 'with ThreadPoolExecutor' followed by 'for provider'
        # NOT: 'for provider' followed by 'with ThreadPoolExecutor'
        lines = source.split("\n")
        executor_lines = [i for i, l in enumerate(lines) if "ThreadPoolExecutor" in l]
        for_lines = [i for i, l in enumerate(lines) if "for provider in" in l]

        # Each executor context should appear BEFORE its provider loop
        assert len(executor_lines) >= 2  # Primary search + category retry
        assert len(for_lines) >= 2

        # First executor should be before first provider loop
        assert executor_lines[0] < for_lines[0]


class TestNewsnabErrorLogging:
    """Verify error logging includes traceback info."""

    def test_search_error_has_exc_info(self):
        """Newsnab search error log should include exc_info=True."""
        import inspect
        from providers.newsnab import NewsnabProvider

        source = inspect.getsource(NewsnabProvider.search)
        # Find the line with "Newsnab search error"
        assert "exc_info=True" in source
