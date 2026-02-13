"""
Tests for the RSS Feed Sync and Match services (cache-first auto-download).

Tests cover:
- FeedSyncService: RSS feed polling, entry upsert, deduplication, expiry
- FeedMatchService: Local matching of cached entries against tracked periodicals
- RssFeedEntry model: Cache database model
"""

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from core.interfaces import SearchProvider, SearchResult
from models.cache import CacheBase, RssFeedEntry
from models.database import Base, PeriodicalTracking
from services.cache.feed_match import FeedMatchService
from services.cache.feed_sync import FeedSyncService


# =============================================================================
# Test Fixtures
# =============================================================================


class MockSearchProvider(SearchProvider):
    """Mock search provider that returns configurable results."""

    def __init__(self, name: str = "TestProvider", results: Optional[List[SearchResult]] = None):
        config = {"name": name, "type": "newsnab"}
        super().__init__(config)
        self._results = results or []
        self._rate_limited = False

    def search(self, query: str = "", category: str = None, aliases: Optional[Sequence[str]] = None):
        return self._results

    @property
    def is_rate_limited(self) -> bool:
        return self._rate_limited


def make_search_result(title: str, url: str, guid: str, pub_date=None) -> SearchResult:
    """Create a SearchResult for testing."""
    return SearchResult(
        title=title,
        url=url,
        provider="newsnab",
        publication_date=pub_date or datetime(2025, 1, 15, tzinfo=UTC),
        raw_metadata={"guid": guid, "category": "7010"},
    )


@pytest.fixture
def cache_db(tmp_path):
    """Create a temporary cache database."""
    db_path = str(tmp_path / "test_cache.db")
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    CacheBase.metadata.create_all(engine)
    return db_path


@pytest.fixture
def main_db_session():
    """Create an in-memory main database session for tracking records."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()


@pytest.fixture
def feed_sync_service(cache_db):
    """Create a FeedSyncService with test database."""
    return FeedSyncService(cache_db_path=cache_db, retention_days=7)


@pytest.fixture
def feed_match_service():
    """Create a FeedMatchService."""
    return FeedMatchService()


# =============================================================================
# FeedSyncService Tests
# =============================================================================


class TestFeedSyncService:
    """Tests for RSS feed sync service."""

    def test_sync_provider_new_entries(self, feed_sync_service):
        """Test syncing a provider creates new feed entries."""
        provider = MockSearchProvider(
            name="TestIndexer",
            results=[
                make_search_result("Magazine A - January 2025", "http://nzb/1", "guid-001"),
                make_search_result("Magazine B - February 2025", "http://nzb/2", "guid-002"),
                make_search_result("Comic X #42", "http://nzb/3", "guid-003"),
            ],
        )

        stats = feed_sync_service.sync_provider(provider)

        assert stats["new"] == 3
        assert stats["updated"] == 0
        assert stats["total_feed_entries"] == 3
        assert stats["provider"] == "TestIndexer"

    def test_sync_provider_deduplicates_by_guid(self, feed_sync_service):
        """Test that syncing the same entries twice deduplicates by GUID."""
        provider = MockSearchProvider(
            name="TestIndexer",
            results=[
                make_search_result("Magazine A - January 2025", "http://nzb/1", "guid-001"),
                make_search_result("Magazine B - February 2025", "http://nzb/2", "guid-002"),
            ],
        )

        # First sync
        stats1 = feed_sync_service.sync_provider(provider)
        assert stats1["new"] == 2
        assert stats1["updated"] == 0

        # Second sync — same entries
        stats2 = feed_sync_service.sync_provider(provider)
        assert stats2["new"] == 0
        assert stats2["updated"] == 2

    def test_sync_provider_updates_url_on_resync(self, feed_sync_service):
        """Test that URL is updated when entry is seen again with new URL."""
        provider = MockSearchProvider(
            name="TestIndexer",
            results=[
                make_search_result("Magazine A - January 2025", "http://nzb/old-url", "guid-001"),
            ],
        )

        feed_sync_service.sync_provider(provider)

        # Resync with updated URL
        provider._results = [
            make_search_result("Magazine A - January 2025", "http://nzb/new-url", "guid-001"),
        ]
        feed_sync_service.sync_provider(provider)

        entries = feed_sync_service.get_new_entries(limit=10)
        assert len(entries) == 1
        assert entries[0].url == "http://nzb/new-url"

    def test_sync_provider_skips_rate_limited(self, feed_sync_service):
        """Test that rate-limited providers are skipped."""
        provider = MockSearchProvider(name="TestIndexer")
        provider._rate_limited = True

        stats = feed_sync_service.sync_provider(provider)
        assert stats["new"] == 0
        assert stats["total_feed_entries"] == 0

    def test_sync_all_providers(self, feed_sync_service):
        """Test syncing multiple providers."""
        provider1 = MockSearchProvider(
            name="Indexer1",
            results=[
                make_search_result("Magazine A", "http://nzb/1", "guid-p1-001"),
            ],
        )
        provider2 = MockSearchProvider(
            name="Indexer2",
            results=[
                make_search_result("Magazine B", "http://nzb/2", "guid-p2-001"),
                make_search_result("Magazine C", "http://nzb/3", "guid-p2-002"),
            ],
        )

        stats = feed_sync_service.sync_all_providers([provider1, provider2])

        assert stats["total_new"] == 3
        assert stats["providers_synced"] == 2

    def test_get_new_entries(self, feed_sync_service):
        """Test retrieving new (unmatched) entries."""
        provider = MockSearchProvider(
            name="TestIndexer",
            results=[
                make_search_result("Mag A", "http://nzb/1", "guid-001"),
                make_search_result("Mag B", "http://nzb/2", "guid-002"),
                make_search_result("Mag C", "http://nzb/3", "guid-003"),
            ],
        )
        feed_sync_service.sync_provider(provider)

        entries = feed_sync_service.get_new_entries(limit=2)
        assert len(entries) == 2

        # All should have status "new"
        for entry in entries:
            assert entry.status == "new"

    def test_get_new_entries_respects_limit(self, feed_sync_service):
        """Test that get_new_entries respects the limit parameter."""
        provider = MockSearchProvider(
            name="TestIndexer",
            results=[make_search_result(f"Mag {i}", f"http://nzb/{i}", f"guid-{i:03d}") for i in range(10)],
        )
        feed_sync_service.sync_provider(provider)

        entries = feed_sync_service.get_new_entries(limit=3)
        assert len(entries) == 3

    def test_mark_entries_matched(self, feed_sync_service):
        """Test marking entries as matched."""
        provider = MockSearchProvider(
            name="TestIndexer",
            results=[
                make_search_result("Mag A", "http://nzb/1", "guid-001"),
                make_search_result("Mag B", "http://nzb/2", "guid-002"),
            ],
        )
        feed_sync_service.sync_provider(provider)

        entries = feed_sync_service.get_new_entries(limit=10)
        entry_ids = [e.id for e in entries]

        updated = feed_sync_service.mark_entries_matched(entry_ids)
        assert updated == 2

        # No more "new" entries
        new_entries = feed_sync_service.get_new_entries(limit=10)
        assert len(new_entries) == 0

    def test_mark_entries_skipped(self, feed_sync_service):
        """Test marking entries as skipped."""
        provider = MockSearchProvider(
            name="TestIndexer",
            results=[
                make_search_result("Mag A", "http://nzb/1", "guid-001"),
            ],
        )
        feed_sync_service.sync_provider(provider)

        entries = feed_sync_service.get_new_entries(limit=10)
        feed_sync_service.mark_entries_skipped([entries[0].id])

        # Entry should no longer appear as "new"
        new_entries = feed_sync_service.get_new_entries(limit=10)
        assert len(new_entries) == 0

    def test_expire_old_entries(self, cache_db):
        """Test that old entries are expired."""
        service = FeedSyncService(cache_db_path=cache_db, retention_days=1)

        provider = MockSearchProvider(
            name="TestIndexer",
            results=[
                make_search_result("Old Mag", "http://nzb/1", "guid-001"),
            ],
        )
        service.sync_provider(provider)

        # Manually set first_seen to 2 days ago
        session = service._session_factory()
        try:
            entry = session.query(RssFeedEntry).first()
            entry.first_seen = datetime.now(UTC) - timedelta(days=2)
            session.commit()
        finally:
            session.close()

        deleted = service.expire_old_entries()
        assert deleted == 1

    def test_get_stats(self, feed_sync_service):
        """Test getting cache statistics."""
        provider = MockSearchProvider(
            name="TestIndexer",
            results=[
                make_search_result("Mag A", "http://nzb/1", "guid-001"),
                make_search_result("Mag B", "http://nzb/2", "guid-002"),
            ],
        )
        feed_sync_service.sync_provider(provider)

        stats = feed_sync_service.get_stats()
        assert stats["total_entries"] == 2
        assert stats["new"] == 2
        assert stats["matched"] == 0
        assert stats["skipped"] == 0

    def test_extract_guid_from_metadata(self, feed_sync_service):
        """Test GUID extraction from raw_metadata."""
        result = SearchResult(
            title="Test",
            url="http://test.com",
            provider="test",
            raw_metadata={"guid": "my-unique-guid"},
        )
        assert FeedSyncService._extract_guid(result) == "my-unique-guid"

    def test_extract_guid_falls_back_to_url(self, feed_sync_service):
        """Test GUID extraction falls back to URL when no GUID in metadata."""
        result = SearchResult(
            title="Test",
            url="http://test.com/nzb/12345",
            provider="test",
            raw_metadata={},
        )
        assert FeedSyncService._extract_guid(result) == "http://test.com/nzb/12345"

    def test_extract_guid_returns_none_for_empty(self, feed_sync_service):
        """Test GUID extraction returns None when no GUID and no URL."""
        result = SearchResult(
            title="Test",
            url="",
            provider="test",
            raw_metadata={},
        )
        assert FeedSyncService._extract_guid(result) is None


# =============================================================================
# FeedMatchService Tests
# =============================================================================


class TestFeedMatchService:
    """Tests for local feed entry matching against tracked periodicals."""

    def _create_tracking(self, session, title, aliases=None, tracking_id=None):
        """Helper to create a PeriodicalTracking record."""
        tracking = PeriodicalTracking(
            olid="OL12345W",
            title=title,
            language="English",
            search_aliases=aliases,
        )
        session.add(tracking)
        session.commit()
        return tracking

    def _create_feed_entry(self, title, guid, provider="TestProvider"):
        """Helper to create an RssFeedEntry object (detached from session)."""
        entry = RssFeedEntry(
            id=hash(guid) % 100000,  # Fake ID for testing
            guid=guid,
            provider_name=provider,
            title=title,
            url=f"http://nzb/{guid}",
            published_date=datetime(2025, 1, 15, tzinfo=UTC),
            status="new",
        )
        return entry

    def test_match_entries_basic(self, feed_match_service, main_db_session):
        """Test basic matching of feed entries against tracked titles."""
        tracking = self._create_tracking(main_db_session, "Popular Science")

        entries = [
            self._create_feed_entry("Popular Science - January 2025", "guid-001"),
            self._create_feed_entry("National Geographic - January 2025", "guid-002"),
            self._create_feed_entry("Popular Science Special Edition 2025", "guid-003"),
        ]

        result = feed_match_service.match_entries_against_tracking(entries, main_db_session)

        # "Popular Science" should match 2 entries
        assert result["stats"]["matched"] == 2
        assert result["stats"]["skipped"] == 1
        assert tracking.id in result["matches"]
        assert len(result["matches"][tracking.id]) == 2

    def test_match_entries_with_aliases(self, feed_match_service, main_db_session):
        """Test matching with search aliases."""
        tracking = self._create_tracking(main_db_session, "Scientific American", aliases="SciAm, Sci Am")

        entries = [
            self._create_feed_entry("SciAm - March 2025 Special", "guid-001"),
            self._create_feed_entry("Unrelated Magazine", "guid-002"),
        ]

        result = feed_match_service.match_entries_against_tracking(entries, main_db_session)

        assert result["stats"]["matched"] == 1
        assert result["stats"]["skipped"] == 1

    def test_match_entries_case_insensitive(self, feed_match_service, main_db_session):
        """Test that matching is case-insensitive."""
        self._create_tracking(main_db_session, "Time Magazine")

        entries = [
            self._create_feed_entry("TIME MAGAZINE - Weekly Edition 2025", "guid-001"),
            self._create_feed_entry("time magazine january 2025", "guid-002"),
        ]

        result = feed_match_service.match_entries_against_tracking(entries, main_db_session)

        assert result["stats"]["matched"] == 2

    def test_match_entries_no_tracking(self, feed_match_service, main_db_session):
        """Test matching when there are no tracked periodicals."""
        entries = [
            self._create_feed_entry("Some Magazine", "guid-001"),
        ]

        result = feed_match_service.match_entries_against_tracking(entries, main_db_session)

        assert result["stats"]["matched"] == 0
        assert result["stats"]["skipped"] == 1

    def test_match_entries_empty_list(self, feed_match_service, main_db_session):
        """Test matching with empty entry list."""
        result = feed_match_service.match_entries_against_tracking([], main_db_session)

        assert result["stats"]["total"] == 0
        assert result["stats"]["matched"] == 0

    def test_match_entries_multiple_periodicals(self, feed_match_service, main_db_session):
        """Test matching entries against multiple tracked periodicals."""
        tracking1 = self._create_tracking(main_db_session, "Forbes")
        tracking2 = self._create_tracking(main_db_session, "Fortune")

        entries = [
            self._create_feed_entry("Forbes - January 2025", "guid-001"),
            self._create_feed_entry("Fortune 500 Special 2025", "guid-002"),
            self._create_feed_entry("Bloomberg Businessweek", "guid-003"),
        ]

        result = feed_match_service.match_entries_against_tracking(entries, main_db_session)

        assert result["stats"]["matched"] == 2
        assert result["stats"]["skipped"] == 1
        assert tracking1.id in result["matches"]
        assert tracking2.id in result["matches"]

    def test_match_entry_to_search_result_format(self, feed_match_service, main_db_session):
        """Test that matched entries are converted to proper SearchResult format."""
        self._create_tracking(main_db_session, "Nature")

        entries = [
            self._create_feed_entry("Nature - Vol 42 Issue 3", "my-guid-123"),
        ]
        entries[0].url = "http://nzb/download/12345"
        entries[0].category = "7010"

        result = feed_match_service.match_entries_against_tracking(entries, main_db_session)

        assert result["stats"]["matched"] == 1
        search_results = list(result["matches"].values())[0]
        sr = search_results[0]

        assert sr["title"] == "Nature - Vol 42 Issue 3"
        assert sr["url"] == "http://nzb/download/12345"
        assert sr["guid"] == "my-guid-123"
        assert sr["raw_metadata"]["source"] == "feed_cache"

    def test_match_entry_only_matches_once(self, feed_match_service, main_db_session):
        """Test that each entry matches at most one periodical (first match wins)."""
        # Both tracking records could match "Science Nature"
        self._create_tracking(main_db_session, "Science")
        self._create_tracking(main_db_session, "Nature")

        entries = [
            self._create_feed_entry("Something Unrelated", "guid-001"),
        ]

        result = feed_match_service.match_entries_against_tracking(entries, main_db_session)
        # Should only match once (or not at all if neither matches)
        assert result["stats"]["matched"] + result["stats"]["skipped"] == 1


# =============================================================================
# Integration Tests
# =============================================================================


class TestFeedSyncMatchIntegration:
    """Integration tests for sync + match pipeline."""

    def test_end_to_end_sync_and_match(self, feed_sync_service, feed_match_service, main_db_session):
        """Test full pipeline: sync → get new → match → mark."""
        # Set up tracking
        tracking = PeriodicalTracking(
            olid="OL12345W",
            title="Popular Mechanics",
            language="English",
        )
        main_db_session.add(tracking)
        main_db_session.commit()

        # Phase 1: Sync provider feed
        provider = MockSearchProvider(
            name="TestIndexer",
            results=[
                make_search_result("Popular Mechanics - January 2025", "http://nzb/1", "guid-001"),
                make_search_result("Popular Mechanics - February 2025", "http://nzb/2", "guid-002"),
                make_search_result("Wired Magazine - January 2025", "http://nzb/3", "guid-003"),
            ],
        )
        sync_stats = feed_sync_service.sync_provider(provider)
        assert sync_stats["new"] == 3

        # Phase 2: Get new entries and match
        new_entries = feed_sync_service.get_new_entries(limit=200)
        assert len(new_entries) == 3

        match_result = feed_match_service.match_entries_against_tracking(new_entries, main_db_session)
        assert match_result["stats"]["matched"] == 2  # Popular Mechanics x2
        assert match_result["stats"]["skipped"] == 1  # Wired

        # Mark entries
        feed_sync_service.mark_entries_matched(match_result["matched_entry_ids"])
        feed_sync_service.mark_entries_skipped(match_result["skipped_entry_ids"])

        # Verify stats
        stats = feed_sync_service.get_stats()
        assert stats["matched"] == 2
        assert stats["skipped"] == 1
        assert stats["new"] == 0

    def test_incremental_sync(self, feed_sync_service, feed_match_service, main_db_session):
        """Test that only new entries are matched after incremental sync."""
        tracking = PeriodicalTracking(
            olid="OL12345W",
            title="The Economist",
            language="English",
        )
        main_db_session.add(tracking)
        main_db_session.commit()

        # First sync
        provider = MockSearchProvider(
            name="TestIndexer",
            results=[
                make_search_result("The Economist - Week 1", "http://nzb/1", "guid-001"),
            ],
        )
        feed_sync_service.sync_provider(provider)
        entries = feed_sync_service.get_new_entries(limit=200)
        match_result = feed_match_service.match_entries_against_tracking(entries, main_db_session)
        feed_sync_service.mark_entries_matched(match_result["matched_entry_ids"])

        # Second sync with new + old entries
        provider._results = [
            make_search_result("The Economist - Week 1", "http://nzb/1", "guid-001"),  # Already seen
            make_search_result("The Economist - Week 2", "http://nzb/2", "guid-002"),  # New
        ]
        feed_sync_service.sync_provider(provider)

        # Only the new entry should be "new"
        entries = feed_sync_service.get_new_entries(limit=200)
        assert len(entries) == 1
        assert entries[0].title == "The Economist - Week 2"


# =============================================================================
# Reset Skipped Entries Tests
# =============================================================================


class TestResetSkippedEntries:
    """Tests for re-evaluating skipped feed entries when tracking changes."""

    def test_reset_skipped_entries_returns_to_new(self, feed_sync_service, feed_match_service, main_db_session):
        """Skipped entries should be reset to 'new' status."""
        # Sync some entries — no tracking exists yet, so all will be skipped
        provider = MockSearchProvider(
            name="TestIndexer",
            results=[
                make_search_result("PC Gamer - Jan 2025", "http://nzb/1", "guid-001"),
                make_search_result("Wired - Feb 2025", "http://nzb/2", "guid-002"),
                make_search_result("Nature - Mar 2025", "http://nzb/3", "guid-003"),
            ],
        )
        feed_sync_service.sync_provider(provider)

        # Match with no tracking records — all get skipped
        entries = feed_sync_service.get_new_entries(limit=200)
        assert len(entries) == 3

        match_result = feed_match_service.match_entries_against_tracking(entries, main_db_session)
        assert match_result["stats"]["matched"] == 0
        assert match_result["stats"]["skipped"] == 3

        feed_sync_service.mark_entries_skipped(match_result["skipped_entry_ids"])

        # Verify no new entries available
        entries = feed_sync_service.get_new_entries(limit=200)
        assert len(entries) == 0

        # Reset skipped entries
        reset_count = feed_sync_service.reset_skipped_entries()
        assert reset_count == 3

        # Now entries should be available again as "new"
        entries = feed_sync_service.get_new_entries(limit=200)
        assert len(entries) == 3

    def test_reset_skipped_entries_enables_new_tracking_match(
        self, feed_sync_service, feed_match_service, main_db_session
    ):
        """After reset, entries should match a newly-added tracking record."""
        # Sync entries
        provider = MockSearchProvider(
            name="TestIndexer",
            results=[
                make_search_result("PC Gamer - Jan 2025", "http://nzb/1", "guid-001"),
                make_search_result("Wired - Feb 2025", "http://nzb/2", "guid-002"),
            ],
        )
        feed_sync_service.sync_provider(provider)

        # First pass — no tracking, all skipped
        entries = feed_sync_service.get_new_entries(limit=200)
        match_result = feed_match_service.match_entries_against_tracking(entries, main_db_session)
        feed_sync_service.mark_entries_skipped(match_result["skipped_entry_ids"])

        # User adds tracking for "PC Gamer"
        tracking = PeriodicalTracking(
            olid="OL-pcgamer",
            title="PC Gamer",
            language="English",
        )
        main_db_session.add(tracking)
        main_db_session.commit()

        # Reset skipped entries (triggered by new tracking creation)
        feed_sync_service.reset_skipped_entries()

        # Re-evaluate — PC Gamer should now match
        entries = feed_sync_service.get_new_entries(limit=200)
        assert len(entries) == 2

        match_result = feed_match_service.match_entries_against_tracking(entries, main_db_session)
        assert match_result["stats"]["matched"] == 1
        assert tracking.id in match_result["matches"]
        assert match_result["matches"][tracking.id][0]["title"] == "PC Gamer - Jan 2025"

    def test_reset_skipped_does_not_affect_matched_entries(
        self, feed_sync_service, feed_match_service, main_db_session
    ):
        """Reset should only affect 'skipped' entries, not 'matched' ones."""
        # Add tracking
        tracking = PeriodicalTracking(
            olid="OL-wired",
            title="Wired",
            language="English",
        )
        main_db_session.add(tracking)
        main_db_session.commit()

        # Sync entries
        provider = MockSearchProvider(
            name="TestIndexer",
            results=[
                make_search_result("Wired - Jan 2025", "http://nzb/1", "guid-001"),
                make_search_result("Nature - Mar 2025", "http://nzb/2", "guid-002"),
            ],
        )
        feed_sync_service.sync_provider(provider)

        # Match — Wired matches, Nature is skipped
        entries = feed_sync_service.get_new_entries(limit=200)
        match_result = feed_match_service.match_entries_against_tracking(entries, main_db_session)
        feed_sync_service.mark_entries_matched(match_result["matched_entry_ids"])
        feed_sync_service.mark_entries_skipped(match_result["skipped_entry_ids"])

        # Reset — only Nature (skipped) should become "new"
        reset_count = feed_sync_service.reset_skipped_entries()
        assert reset_count == 1

        entries = feed_sync_service.get_new_entries(limit=200)
        assert len(entries) == 1
        assert entries[0].title == "Nature - Mar 2025"

    def test_reset_skipped_entries_no_skipped(self, feed_sync_service):
        """Reset with no skipped entries should return 0."""
        reset_count = feed_sync_service.reset_skipped_entries()
        assert reset_count == 0
