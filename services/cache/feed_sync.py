"""
RSS Feed Sync Service — Phase 1 of cache-first auto-download.

Polls each provider's RSS feed periodically (single HTTP GET per provider),
parses entries, and upserts them into the RssFeedEntry cache table. This
decouples feed discovery (cheap) from per-periodical matching (local-only),
preventing rate limiting even with hundreds of tracked periodicals.

Architecture:
    1. Feed Sync (this service): Polls RSS → upserts RssFeedEntry rows
    2. Local Match (FeedMatchService): Matches cached entries against tracking rules
    3. Download Queue: Standard issue discovery flow handles downloads

The key insight: RSS polling is one GET per provider. Rate limiting happens
when you search per-periodical. By caching all entries locally first, matching
becomes a local database operation with zero API calls.
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from core.constants.app import FEED_ENTRY_RETENTION_DAYS
from core.interfaces import SearchProvider
from core.parsers import utc_now
from models.cache import CacheBase, RssFeedEntry

logger = logging.getLogger(__name__)


class FeedSyncService:
    """
    Synchronize RSS feed entries from providers into the local cache.

    Performs lightweight RSS polling (one HTTP GET per provider) and upserts
    entries into RssFeedEntry table. Handles deduplication via GUID, tracks
    high-water marks, and expires old entries.
    """

    def __init__(self, cache_db_path: str, retention_days: int = FEED_ENTRY_RETENTION_DAYS, session_factory=None):
        """
        Initialize the feed sync service.

        Args:
            cache_db_path: Path to cache SQLite database
            retention_days: Days to retain feed entries before expiring
            session_factory: Optional pre-built sessionmaker for shared engine usage.
                             If not provided, creates its own engine (backward compatible).
        """
        self.cache_db_path = cache_db_path
        self.retention_days = retention_days

        if session_factory is not None:
            # Use shared engine/session factory (preferred — avoids duplicate connections)
            self._session_factory = session_factory
        else:
            # Create own engine (backward compatible for tests and standalone usage)
            db_url = f"sqlite:///{cache_db_path}"
            self._engine = create_engine(db_url, echo=False)
            self._session_factory = sessionmaker(bind=self._engine)
            CacheBase.metadata.create_all(self._engine)

        logger.info(f"Feed sync service initialized: {cache_db_path} (retention: {retention_days} days)")

    def sync_provider(self, provider: SearchProvider) -> Dict[str, int]:
        """
        Sync RSS feed from a single provider into the cache.

        Fetches the provider's RSS feed (single HTTP GET), parses entries,
        and upserts into RssFeedEntry. Uses GUID for deduplication.

        Args:
            provider: SearchProvider instance to sync from

        Returns:
            Dict with stats: {new, updated, total_feed_entries, provider}
        """
        stats = {"new": 0, "updated": 0, "total_feed_entries": 0, "provider": provider.name, "errors": 0}

        # Skip rate-limited providers
        if provider.is_rate_limited:
            logger.debug(f"[FeedSync] Skipping '{provider.name}' — rate limited")
            return stats

        try:
            # Use empty query to trigger RSS mode — fetches latest releases
            # This is a single HTTP GET, the cheapest possible API call
            results = provider.search(query="", category=None)
            stats["total_feed_entries"] = len(results)

            if not results:
                logger.debug(f"[FeedSync] No entries from '{provider.name}'")
                return stats

            session = self._session_factory()
            try:
                now = utc_now()

                for result in results:
                    try:
                        # Extract GUID for deduplication
                        guid = self._extract_guid(result)
                        if not guid:
                            stats["errors"] += 1
                            continue

                        # Check if entry already exists
                        existing = (
                            session.query(RssFeedEntry)
                            .filter(
                                RssFeedEntry.provider_name == provider.name,
                                RssFeedEntry.guid == guid,
                            )
                            .first()
                        )

                        if existing:
                            # Update last_seen timestamp and URL (may change)
                            existing.last_seen = now
                            if result.url:
                                existing.url = result.url
                            # Update provider_type if not set (for backwards compatibility)
                            if not existing.provider_type:
                                existing.provider_type = provider.type
                            stats["updated"] += 1
                        else:
                            # New entry
                            raw_meta = json.dumps(result.raw_metadata) if result.raw_metadata else None
                            category = result.raw_metadata.get("category") if result.raw_metadata else None

                            entry = RssFeedEntry(
                                guid=guid,
                                provider_name=provider.name,
                                provider_type=provider.type,
                                title=result.title,
                                url=result.url or "",
                                published_date=result.publication_date,
                                status="new",
                                first_seen=now,
                                last_seen=now,
                                category=category,
                                raw_metadata=raw_meta,
                            )
                            session.add(entry)
                            stats["new"] += 1

                    except Exception as e:
                        logger.warning(f"[FeedSync] Error processing entry from '{provider.name}': {e}")
                        stats["errors"] += 1

                try:
                    session.commit()
                except Exception as e:
                    session.rollback()
                    logger.error(f"[FeedSync] Failed to commit feed entries for '{provider.name}': {e}")
                    raise

                if stats["new"] > 0:
                    logger.info(
                        f"[FeedSync] '{provider.name}': {stats['new']} new, "
                        f"{stats['updated']} updated out of {stats['total_feed_entries']} entries"
                    )
                else:
                    logger.debug(
                        f"[FeedSync] '{provider.name}': {stats['updated']} updated, "
                        f"0 new out of {stats['total_feed_entries']} entries"
                    )

            finally:
                session.close()

        except Exception as e:
            logger.error(f"[FeedSync] Error syncing '{provider.name}': {e}", exc_info=True)

        return stats

    def sync_all_providers(self, providers: List[SearchProvider]) -> Dict[str, Any]:
        """
        Sync RSS feeds from all providers.

        This is the main entry point for the feed sync task. Iterates through
        providers and syncs each one. Providers are polled sequentially with
        staggered timing handled naturally by the scheduler.

        Args:
            providers: List of SearchProvider instances

        Returns:
            Aggregate stats dict
        """
        aggregate = {
            "providers_synced": 0,
            "providers_skipped": 0,
            "total_new": 0,
            "total_updated": 0,
            "total_errors": 0,
            "provider_stats": [],
        }

        for provider in providers:
            try:
                stats = self.sync_provider(provider)
                aggregate["provider_stats"].append(stats)
                aggregate["total_new"] += stats["new"]
                aggregate["total_updated"] += stats["updated"]
                aggregate["total_errors"] += stats["errors"]

                if stats["total_feed_entries"] > 0:
                    aggregate["providers_synced"] += 1
                else:
                    aggregate["providers_skipped"] += 1

            except Exception as e:
                logger.error(f"[FeedSync] Failed to sync provider '{provider.name}': {e}")
                aggregate["providers_skipped"] += 1

        if aggregate["total_new"] > 0:
            logger.info(
                f"[FeedSync] Sync complete: {aggregate['total_new']} new entries, "
                f"{aggregate['total_updated']} updated across {aggregate['providers_synced']} providers"
            )

        return aggregate

    def get_new_entries(self, limit: int = 200) -> List[RssFeedEntry]:
        """
        Get unmatched (status='new') entries for batch matching.

        Returns the oldest-first entries that haven't been matched against
        tracking rules yet. This is the bridge between Phase 1 (sync) and
        Phase 2 (match).

        Args:
            limit: Maximum entries to return (default: 200)

        Returns:
            List of RssFeedEntry objects with status='new'
        """
        session = self._session_factory()
        try:
            entries = (
                session.query(RssFeedEntry)
                .filter(RssFeedEntry.status == "new")
                .order_by(RssFeedEntry.first_seen.asc())
                .limit(limit)
                .all()
            )
            # Detach from session so they can be used outside
            session.expunge_all()
            return entries
        finally:
            session.close()

    def mark_entries_matched(self, entry_ids: List[int]) -> int:
        """
        Mark entries as matched (they've been forwarded to issue discovery).

        Args:
            entry_ids: List of RssFeedEntry IDs to mark

        Returns:
            Number of entries updated
        """
        if not entry_ids:
            return 0

        session = self._session_factory()
        try:
            updated = (
                session.query(RssFeedEntry)
                .filter(RssFeedEntry.id.in_(entry_ids))
                .update({"status": "matched"}, synchronize_session=False)
            )
            session.commit()
            return updated
        finally:
            session.close()

    def mark_entries_skipped(self, entry_ids: List[int]) -> int:
        """
        Mark entries as skipped (don't match any tracked periodical).

        Args:
            entry_ids: List of RssFeedEntry IDs to mark

        Returns:
            Number of entries updated
        """
        if not entry_ids:
            return 0

        session = self._session_factory()
        try:
            updated = (
                session.query(RssFeedEntry)
                .filter(RssFeedEntry.id.in_(entry_ids))
                .update({"status": "skipped"}, synchronize_session=False)
            )
            session.commit()
            return updated
        finally:
            session.close()

    def expire_old_entries(self) -> int:
        """
        Expire entries older than the retention window.

        Deletes entries with first_seen older than retention_days.
        Called periodically to keep the cache bounded.

        Returns:
            Number of entries deleted
        """
        session = self._session_factory()
        try:
            cutoff = utc_now() - timedelta(days=self.retention_days)
            deleted = (
                session.query(RssFeedEntry).filter(RssFeedEntry.first_seen < cutoff).delete(synchronize_session=False)
            )
            session.commit()

            if deleted > 0:
                logger.info(f"[FeedSync] Expired {deleted} entries older than {self.retention_days} days")

            return deleted
        finally:
            session.close()

    def reset_skipped_entries(self) -> int:
        """
        Reset all 'skipped' entries back to 'new' for re-evaluation.

        Called when tracking records change (new tracking added, title or
        aliases updated) so previously-skipped entries get matched against
        the updated tracking rules.

        Returns:
            Number of entries reset
        """
        session = self._session_factory()
        try:
            reset_count = (
                session.query(RssFeedEntry)
                .filter(RssFeedEntry.status == "skipped")
                .update({"status": "new"}, synchronize_session=False)
            )
            session.commit()

            if reset_count > 0:
                logger.info(
                    f"[FeedSync] Reset {reset_count} skipped entries to 'new' "
                    f"for re-evaluation against updated tracking rules"
                )

            return reset_count
        finally:
            session.close()

    def get_stats(self) -> Dict[str, Any]:
        """
        Get feed sync cache statistics.

        Returns:
            Dict with cache stats by status and provider
        """
        session = self._session_factory()
        try:
            total = session.query(RssFeedEntry).count()
            new = session.query(RssFeedEntry).filter(RssFeedEntry.status == "new").count()
            matched = session.query(RssFeedEntry).filter(RssFeedEntry.status == "matched").count()
            skipped = session.query(RssFeedEntry).filter(RssFeedEntry.status == "skipped").count()

            return {
                "total_entries": total,
                "new": new,
                "matched": matched,
                "skipped": skipped,
            }
        finally:
            session.close()

    @staticmethod
    def _extract_guid(result) -> Optional[str]:
        """
        Extract a unique GUID from a search result.

        Tries raw_metadata["guid"] first, falls back to URL hash.

        Args:
            result: SearchResult from a provider

        Returns:
            GUID string, or None if no usable identifier
        """
        # Try GUID from metadata
        if result.raw_metadata:
            guid = result.raw_metadata.get("guid")
            if guid:
                return str(guid)

        # Fall back to URL as unique identifier
        if result.url:
            return result.url

        return None
