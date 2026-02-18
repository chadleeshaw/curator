"""
Tests for medium severity architecture fixes:
1. Shared cache engine — FeedSyncService and NzbCacheService accept shared session factory
2. SearchResult periodic cleanup — SEARCH_RESULT_RETENTION_DAYS constant exists
3. Download slot race condition — DownloadManager._slot_lock serializes concurrent access
"""

import sys
import threading
import time
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from core.parsers.date import utc_now

from core.interfaces import DownloadClient
from models.cache import CacheBase, NzbCache, RssFeedEntry
from models.database import Base, DownloadSubmission, DiscoveredIssue, PeriodicalTracking, SearchResult
from services.cache.feed_sync import FeedSyncService
from services.cache.provider_cache import NzbCacheService


# =============================================================================
# Fix 1: Shared cache engine
# =============================================================================


class TestSharedCacheEngine:
    """Verify both cache services accept and use an injected session factory."""

    @pytest.fixture
    def shared_cache_db(self, tmp_path):
        """Create a shared engine/session factory for both services."""
        db_path = str(tmp_path / "shared_cache.db")
        engine = create_engine(f"sqlite:///{db_path}", echo=False)
        CacheBase.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine)
        return db_path, engine, session_factory

    def test_feed_sync_uses_shared_session_factory(self, shared_cache_db):
        """FeedSyncService should use injected session_factory and NOT create its own engine."""
        db_path, engine, session_factory = shared_cache_db
        service = FeedSyncService(
            cache_db_path=db_path,
            session_factory=session_factory,
        )
        # Should use the injected session factory
        assert service._session_factory is session_factory
        # Should NOT have created its own engine attribute
        assert not hasattr(service, "_engine")

    def test_nzb_cache_uses_shared_session_factory(self, shared_cache_db):
        """NzbCacheService should use injected session_factory and set _engine to None."""
        db_path, engine, session_factory = shared_cache_db
        service = NzbCacheService(
            cache_db_path=db_path,
            session_factory=session_factory,
        )
        assert service._session_factory is session_factory
        assert service._engine is None

    def test_both_services_share_same_session_factory(self, shared_cache_db):
        """Both services should use the exact same session factory instance."""
        db_path, engine, session_factory = shared_cache_db
        feed_service = FeedSyncService(cache_db_path=db_path, session_factory=session_factory)
        nzb_service = NzbCacheService(cache_db_path=db_path, session_factory=session_factory)
        assert feed_service._session_factory is nzb_service._session_factory

    def test_feed_sync_backward_compatible_without_session_factory(self, tmp_path):
        """FeedSyncService should still work without session_factory (creates own engine)."""
        db_path = str(tmp_path / "standalone_cache.db")
        service = FeedSyncService(cache_db_path=db_path)
        # Should have created its own engine
        assert hasattr(service, "_engine")
        assert service._session_factory is not None
        # Verify it works — write and read
        stats = service.get_stats()
        assert stats["total_entries"] == 0

    def test_nzb_cache_backward_compatible_without_session_factory(self, tmp_path):
        """NzbCacheService should still work without session_factory (creates own engine)."""
        db_path = str(tmp_path / "standalone_cache.db")
        service = NzbCacheService(cache_db_path=db_path)
        assert service._engine is not None
        assert service._session_factory is not None
        stats = service.get_stats()
        assert stats["total_cached_nzbs"] == 0

    def test_shared_engine_data_visible_across_services(self, shared_cache_db):
        """Data written by one service should be visible to the other (same DB)."""
        db_path, engine, session_factory = shared_cache_db
        feed_service = FeedSyncService(cache_db_path=db_path, session_factory=session_factory)
        nzb_service = NzbCacheService(cache_db_path=db_path, session_factory=session_factory)

        # Write a feed entry via feed service's session factory
        session = feed_service._session_factory()
        try:
            entry = RssFeedEntry(
                guid="test-guid",
                provider_name="TestProvider",
                title="Test Entry",
                url="http://example.com/test",
                status="new",
                first_seen=utc_now(),
                last_seen=utc_now(),
            )
            session.add(entry)
            session.commit()
        finally:
            session.close()

        # Verify visible from nzb service's session factory (same factory)
        session2 = nzb_service._session_factory()
        try:
            count = session2.query(RssFeedEntry).count()
            assert count == 1
        finally:
            session2.close()


# =============================================================================
# Fix 2: SearchResult retention constant
# =============================================================================


class TestSearchResultCleanup:
    """Verify the SEARCH_RESULT_RETENTION_DAYS constant exists and is reasonable."""

    def test_search_result_retention_constant_exists(self):
        """SEARCH_RESULT_RETENTION_DAYS should be defined in app constants."""
        from core.constants.app import SEARCH_RESULT_RETENTION_DAYS

        assert isinstance(SEARCH_RESULT_RETENTION_DAYS, int)
        assert SEARCH_RESULT_RETENTION_DAYS > 0

    def test_search_result_retention_default_value(self):
        """Default retention should be 30 days."""
        from core.constants.app import SEARCH_RESULT_RETENTION_DAYS

        assert SEARCH_RESULT_RETENTION_DAYS == 30

    def test_search_result_created_at_is_indexed(self):
        """SearchResult.created_at should be indexed for efficient cleanup queries."""
        from models.database import SearchResult

        created_at_col = SearchResult.__table__.columns["created_at"]
        assert created_at_col.index is True

    def test_search_result_cleanup_deletes_old_rows(self, tmp_path):
        """Simulate the Phase 4 cleanup logic to verify it works on old rows."""
        engine = create_engine("sqlite:///:memory:", echo=False)
        Base.metadata.create_all(engine)
        session_factory = sessionmaker(bind=engine)
        session = session_factory()

        try:
            # Insert an old search result (60 days ago)
            old_result = SearchResult(
                provider="newsnab",
                query="test",
                title="Old Result",
                url="http://example.com/old",
                created_at=utc_now() - timedelta(days=60),
            )
            # Insert a recent search result (5 days ago)
            recent_result = SearchResult(
                provider="newsnab",
                query="test",
                title="Recent Result",
                url="http://example.com/recent",
                created_at=utc_now() - timedelta(days=5),
            )
            session.add_all([old_result, recent_result])
            session.commit()

            # Apply cleanup with 30-day retention
            cutoff = utc_now() - timedelta(days=30)
            deleted = (
                session.query(SearchResult).filter(SearchResult.created_at < cutoff).delete(synchronize_session=False)
            )
            session.commit()

            assert deleted == 1  # Only old result deleted
            remaining = session.query(SearchResult).all()
            assert len(remaining) == 1
            assert remaining[0].title == "Recent Result"
        finally:
            session.close()


# =============================================================================
# Fix 3: Download slot race condition
# =============================================================================


class TestDownloadSlotLock:
    """Verify DownloadManager uses a lock to serialize slot-aware submissions."""

    @pytest.fixture
    def mock_download_manager(self):
        """Create a DownloadManager with mocked dependencies."""
        from services.download_manager import DownloadManager

        mock_client = MagicMock(spec=DownloadClient)
        mock_client.config = {"default_category": "magazines"}
        mock_client.name = "test-client"
        mock_provider = MagicMock()
        mock_provider.name = "TestProvider"
        mock_provider.type = "newsnab"

        dm = DownloadManager(
            search_providers=[mock_provider],
            download_client=mock_client,
            max_downloads=5,
        )
        return dm

    def test_download_manager_has_slot_lock(self, mock_download_manager):
        """DownloadManager should have a threading.Lock for slot coordination."""
        assert hasattr(mock_download_manager, "_slot_lock")
        assert isinstance(mock_download_manager._slot_lock, type(threading.Lock()))

    def test_process_queue_acquires_lock(self, mock_download_manager):
        """process_queue() should acquire _slot_lock before processing."""
        dm = mock_download_manager

        # Create a mock session
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.count.return_value = 0
        mock_session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
            []
        )

        # Replace lock with a tracking version
        acquired = []
        original_lock = dm._slot_lock

        class TrackingLock:
            def __enter__(self):
                acquired.append(True)
                return original_lock.__enter__()

            def __exit__(self, *args):
                return original_lock.__exit__(*args)

        dm._slot_lock = TrackingLock()
        dm.process_queue(mock_session)
        assert len(acquired) == 1, "Lock should have been acquired once"

    def test_submit_discovered_batch_acquires_lock(self, mock_download_manager):
        """submit_discovered_batch() should acquire _slot_lock before counting slots."""
        dm = mock_download_manager

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.count.return_value = 5  # At capacity

        mock_discovery = MagicMock()

        acquired = []
        original_lock = dm._slot_lock

        class TrackingLock:
            def __enter__(self):
                acquired.append(True)
                return original_lock.__enter__()

            def __exit__(self, *args):
                return original_lock.__exit__(*args)

        dm._slot_lock = TrackingLock()
        result = dm.submit_discovered_batch(mock_session, mock_discovery)
        assert len(acquired) == 1, "Lock should have been acquired once"
        assert result == 0  # At capacity, nothing submitted

    def test_submit_discovered_batch_respects_max_downloads(self, mock_download_manager):
        """submit_discovered_batch() should not exceed max_downloads."""
        dm = mock_download_manager

        mock_session = MagicMock()
        # 3 active → 2 slots remaining (max=5)
        mock_session.query.return_value.filter.return_value.count.return_value = 3

        mock_issue1 = MagicMock()
        mock_issue1.id = 1
        mock_issue1.title = "Issue 1"
        mock_issue1.download_priority = 1
        mock_issue2 = MagicMock()
        mock_issue2.id = 2
        mock_issue2.title = "Issue 2"
        mock_issue2.download_priority = 2

        mock_discovery = MagicMock()
        mock_discovery.get_download_queue.return_value = [mock_issue1, mock_issue2]

        mock_submission = MagicMock()
        mock_submission.job_id = "job-123"
        dm.submit_from_discovered_issue = MagicMock(return_value=mock_submission)

        result = dm.submit_discovered_batch(mock_session, mock_discovery)

        assert result == 2
        # Verify limit=2 was passed (remaining slots)
        mock_discovery.get_download_queue.assert_called_once_with(mock_session, limit=2)

    def test_concurrent_access_serialized(self, mock_download_manager):
        """Two concurrent callers should never both be inside the lock simultaneously."""
        dm = mock_download_manager
        inside_lock = []
        max_concurrent = [0]
        errors = []

        original_process = dm.queue_processor.process_queue

        def slow_process(session):
            inside_lock.append(1)
            current = len(inside_lock)
            if current > max_concurrent[0]:
                max_concurrent[0] = current
            time.sleep(0.05)  # Simulate work
            inside_lock.pop()
            return {"checked": 0, "submitted": 0, "skipped": 0, "errors": []}

        dm.queue_processor.process_queue = slow_process

        mock_session = MagicMock()

        threads = []
        for _ in range(3):
            t = threading.Thread(target=dm.process_queue, args=(mock_session,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=5)

        assert max_concurrent[0] <= 1, f"Expected max 1 concurrent, got {max_concurrent[0]}"
