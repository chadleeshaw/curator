"""
Provider cache services for caching search provider results.

This module provides two main services:
1. ProviderCacheService: Manages cached releases from search providers
2. ProviderSyncService: Syncs with search providers in background

The cache uses a separate SQLite database with FTS5 full-text search
for fast local searching without hitting provider APIs. Download URLs
are stored in the database and used by download clients when needed.

Classes:
    ProviderCacheService: Manages cached releases from search providers
    ProviderSyncService: Syncs with search providers in background
"""

import hashlib
import logging
import os
import shutil
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests
from sqlalchemy import create_engine, func, text
from sqlalchemy.orm import Session, sessionmaker

from core.constants.cache import (
    CACHE_CLEANUP_BATCH_SIZE,
    CACHE_DB_FILENAME,
    CACHE_RETENTION_DAYS,
    FTS5_TOKENIZER,
    FUZZY_MATCH_SIMILARITY_THRESHOLD,
    INCREMENTAL_SYNC_LIMIT,
    INITIAL_SYNC_LIMIT,
    UPLOAD_DATE_FORMATS,
)
from core.parsers import utc_now
from core.parsers.title import TitleMatcher
from core.utils import run_in_thread
from models.cache import CacheBase, CachedRelease, SyncStatus

logger = logging.getLogger(__name__)


class ProviderCacheService:
    """
    Manages cached search results from providers.

    Provides fast local searching of previously-fetched results with
    FTS5 full-text search and deduplication. Download URLs are stored
    and used by download clients when needed.
    """

    def __init__(
        self,
        cache_db_path: str,
        fuzzy_threshold: int = FUZZY_MATCH_SIMILARITY_THRESHOLD,
    ):
        """
        Initialize provider cache service.

        Args:
            cache_db_path: Path to cache SQLite database
            fuzzy_threshold: Threshold for fuzzy matching (0-100)
        """
        self.cache_db_path = cache_db_path
        self.fuzzy_threshold = fuzzy_threshold

        # Ensure cache directory exists
        cache_dir = os.path.dirname(cache_db_path)
        os.makedirs(cache_dir, exist_ok=True)

        # Initialize database connection
        db_url = f"sqlite:///{cache_db_path}"
        self._engine = create_engine(db_url, echo=False)
        self._session_factory = sessionmaker(bind=self._engine)

        # Create tables and FTS5 index
        self._initialize_database()

        logger.info(f"Provider cache initialized: {cache_db_path}")

    def _initialize_database(self):
        """Create database tables and FTS5 virtual table for full-text search"""
        # Create all tables
        CacheBase.metadata.create_all(self._engine)

        # Create FTS5 virtual table for full-text search on title
        with self._engine.connect() as conn:
            # Check if FTS5 table exists
            result = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='cached_releases_fts'")
            )
            if not result.fetchone():
                # Create FTS5 virtual table
                conn.execute(
                    text(
                        f"""
                        CREATE VIRTUAL TABLE cached_releases_fts USING fts5(
                            title,
                            content='cached_releases',
                            content_rowid='id',
                            tokenize='{FTS5_TOKENIZER}'
                        )
                        """
                    )
                )

                # Create triggers to keep FTS5 in sync
                conn.execute(
                    text(
                        """
                        CREATE TRIGGER cached_releases_fts_insert AFTER INSERT ON cached_releases BEGIN
                            INSERT INTO cached_releases_fts(rowid, title) VALUES (new.id, new.title);
                        END;
                        """
                    )
                )

                conn.execute(
                    text(
                        """
                        CREATE TRIGGER cached_releases_fts_delete AFTER DELETE ON cached_releases BEGIN
                            INSERT INTO cached_releases_fts(cached_releases_fts, rowid, title)
                            VALUES('delete', old.id, old.title);
                        END;
                        """
                    )
                )

                conn.execute(
                    text(
                        """
                        CREATE TRIGGER cached_releases_fts_update AFTER UPDATE ON cached_releases BEGIN
                            INSERT INTO cached_releases_fts(cached_releases_fts, rowid, title)
                            VALUES('delete', old.id, old.title);
                            INSERT INTO cached_releases_fts(rowid, title) VALUES (new.id, new.title);
                        END;
                        """
                    )
                )

                conn.commit()
                logger.info("Created FTS5 virtual table for full-text search")

    def search(
        self,
        query: str,
        category: Optional[str] = None,
        language: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Search cached releases using FTS5 full-text search.

        Args:
            query: Search query
            category: Optional category filter
            language: Optional language filter
            limit: Maximum number of results (default: 50)

        Returns:
            List of matching releases as dictionaries
        """
        session = self._session_factory()
        try:
            # Use FTS5 for full-text search
            sql_query = text(
                """
                SELECT cr.* FROM cached_releases cr
                INNER JOIN cached_releases_fts fts ON cr.id = fts.rowid
                WHERE cached_releases_fts MATCH :query
                """
            )

            params = {"query": query}

            # Add category filter if specified
            if category:
                sql_query = text(str(sql_query) + " AND cr.category = :category")
                params["category"] = category

            # Add language filter if specified
            if language:
                sql_query = text(str(sql_query) + " AND cr.language = :language")
                params["language"] = language

            # Order by upload_date (newest first), then last_seen
            sql_query = text(str(sql_query) + " ORDER BY cr.upload_date DESC, cr.last_seen DESC LIMIT :limit")
            params["limit"] = limit

            # Execute query
            result = session.execute(sql_query, params)
            rows = result.fetchall()

            # Convert to CachedRelease objects and then to dicts
            releases = []
            for row in rows:
                release = session.get(CachedRelease, row[0])  # row[0] is the id
                if release:
                    releases.append(release.to_dict())

            logger.info(f"Cache search: found {len(releases)} results for query '{query}'")
            return releases

        finally:
            session.close()

    def resolve_redirect_url(self, url: str, max_redirects: int = 10) -> str:
        """
        Resolve proxy URLs to final NZB download URLs.

        For providers like Prowlarr that use proxy URLs, this follows redirects
        to get the actual indexer NZB URL. Uses GET with stream=True to avoid
        downloading content while still following redirects.

        Args:
            url: Original download URL (may be a proxy URL)
            max_redirects: Maximum number of redirects to follow (default: 10)

        Returns:
            Final resolved URL after following redirects, or original URL if resolution fails

        Example:
            >>> # Prowlarr proxy URL
            >>> proxy_url = "https://prowlarr.com/download?link=..."
            >>> service.resolve_redirect_url(proxy_url)
            "https://api.nzb.su/getnzb/abc123.nzb&i=..."
        """
        try:
            # Use GET with stream=True to follow redirects without downloading content
            # HEAD requests don't work with Prowlarr/Cloudflare (returns 405)
            response = requests.get(
                url,
                allow_redirects=True,
                timeout=10,
                stream=True,  # Don't download body
            )

            # Close connection immediately (don't download content)
            response.close()

            # Get final URL after redirects
            final_url = response.url

            # Log only if redirect occurred
            if final_url != url:
                redirect_count = len(response.history)
                logger.info(
                    f"Resolved proxy URL ({redirect_count} redirect{'s' if redirect_count > 1 else ''}): "
                    f"{url[:80]}... -> {final_url[:80]}..."
                )

            return final_url

        except requests.exceptions.TooManyRedirects:
            logger.warning(f"Too many redirects resolving URL (>{max_redirects}), using original")
            return url
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to resolve URL redirect: {e}, using original URL")
            return url
        except Exception as e:
            logger.error(f"Unexpected error resolving URL: {e}", exc_info=True)
            return url

    def upsert_releases(self, releases: List[Dict[str, Any]]) -> int:
        """
        Insert or update releases in cache.

        Handles deduplication by GUID. If a release with the same GUID exists:
        - If new upload_date is newer, replace the entire record
        - Otherwise, just update last_seen timestamp

        Args:
            releases: List of release dictionaries from providers

        Returns:
            Number of releases added or updated
        """
        session = self._session_factory()
        try:
            added_count = 0
            updated_count = 0

            for release_data in releases:
                guid = release_data.get("guid")
                if not guid:
                    logger.warning("Skipping release without GUID")
                    continue

                # Check if release already exists
                existing = session.query(CachedRelease).filter(CachedRelease.guid == guid).first()

                if existing:
                    # Compare upload dates
                    new_upload_date = release_data.get("upload_date")
                    existing_upload_date = existing.upload_date

                    if new_upload_date and existing_upload_date and new_upload_date > existing_upload_date:
                        # Newer upload - replace entire record
                        logger.debug(f"Replacing {guid} with newer upload ({new_upload_date} > {existing_upload_date})")
                        session.delete(existing)
                        session.flush()  # Ensure delete is committed before insert

                        # Create new record
                        new_release = self._create_release_from_dict(release_data)
                        session.add(new_release)
                        added_count += 1
                    else:
                        # Same or older upload - just update last_seen
                        existing.last_seen = utc_now()
                        updated_count += 1
                else:
                    # New release - add to cache
                    new_release = self._create_release_from_dict(release_data)
                    session.add(new_release)
                    added_count += 1

            session.commit()
            logger.debug(f"Upserted {added_count} new releases, updated {updated_count} existing releases")
            return added_count + updated_count

        except Exception as e:
            session.rollback()
            logger.error(f"Error upserting releases: {e}", exc_info=True)
            raise
        finally:
            session.close()

    def _create_release_from_dict(self, release_data: Dict[str, Any]) -> CachedRelease:
        """
        Create CachedRelease model from dictionary.

        Args:
            release_data: Release data from provider

        Returns:
            CachedRelease model instance
        """
        # Normalize title for better matching
        title = release_data.get("title", "")
        title_matcher = TitleMatcher()
        normalized_title = title_matcher.clean_release_title(title).lower()

        # Get download URL and resolve any redirects (e.g., Prowlarr proxy URLs)
        download_url = release_data.get("download_url", release_data.get("url", ""))
        resolved_url = self.resolve_redirect_url(download_url)

        return CachedRelease(  # pylint: disable=inconsistent-return-statements
            guid=release_data.get("guid"),
            title=title,
            normalized_title=normalized_title,
            provider_name=release_data.get("provider_name"),
            provider_type=release_data.get("provider_type"),
            download_url=resolved_url,  # Store resolved URL, not proxy
            size_bytes=release_data.get("size_bytes"),
            publication_date=release_data.get("publication_date"),
            upload_date=release_data.get("upload_date"),
            category=release_data.get("category"),
            language=release_data.get("language"),
            country=release_data.get("country"),
            fuzzy_match_group=release_data.get("fuzzy_match_group"),
            raw_metadata=release_data.get("raw_metadata", {}),
        )

    def cleanup_stale_releases(self, days: int = CACHE_RETENTION_DAYS) -> Dict[str, int]:
        """
        Remove releases older than specified days.

        Args:
            days: Number of days to retain (default: 90)

        Returns:
            Dictionary with cleanup statistics
        """
        session = self._session_factory()
        try:
            cutoff_date = datetime.now() - timedelta(days=days)

            # Find stale releases
            stale_releases = (
                session.query(CachedRelease)
                .filter(CachedRelease.last_seen < cutoff_date)
                .limit(CACHE_CLEANUP_BATCH_SIZE)
                .all()
            )

            releases_deleted = len(stale_releases)

            # Delete release records
            for release in stale_releases:
                session.delete(release)

            session.commit()

            logger.info(f"Cleanup complete: deleted {releases_deleted} releases")

            return {"releases_deleted": releases_deleted}

        finally:
            session.close()

    def get_stats(self) -> Dict[str, Any]:
        """
        Get real-time cache statistics by querying the database.

        Returns:
            Dictionary with cache statistics
        """
        session = self._session_factory()
        try:
            # Query database for stats
            total_releases = session.query(CachedRelease).count()

            # Provider breakdown
            providers = (
                session.query(
                    CachedRelease.provider_name,
                    func.count(CachedRelease.id),  # pylint: disable=not-callable
                )
                .group_by(CachedRelease.provider_name)
                .all()
            )

            # Date range
            oldest = session.query(func.min(CachedRelease.first_seen)).scalar()
            newest = session.query(func.max(CachedRelease.last_seen)).scalar()

            # Last sync time (most recent across all providers)
            last_sync = session.query(func.max(SyncStatus.last_successful_sync)).scalar()

            return {
                "total_releases": total_releases,
                "providers": [{"name": name, "count": count} for name, count in providers],
                "oldest_release": oldest.isoformat() if oldest else None,
                "newest_release": newest.isoformat() if newest else None,
                "last_sync": last_sync.isoformat() if last_sync else None,
            }

        finally:
            session.close()

    def purge_all(self) -> Dict[str, Any]:
        """
        Completely purge the cache and reset all sync state.

        This performs a full cache reset:
        1. Drops all database tables (releases + sync status)
        2. Deletes the database file
        3. Next sync will start fresh as if first run

        Returns:
            Statistics about what was deleted
        """
        logger.info("Performing FULL cache purge (reset sync markers)")

        try:
            # Get stats BEFORE purging (DB will be gone after)
            stats = self.get_stats()

            # 1. Close database connection
            if hasattr(self, "_engine") and self._engine:
                self._engine.dispose()
                logger.debug("Disposed database engine")

            # 2. Delete database file (includes all tables and sync markers)
            if os.path.exists(self.cache_db_path):
                os.remove(self.cache_db_path)
                logger.info(f"Deleted cache database: {self.cache_db_path}")

            logger.info(
                f"✓ Cache purge complete: "
                f"{stats['total_releases']} releases deleted. "
                f"All sync markers reset - next sync will rebuild from scratch."
            )

            return {
                "releases_deleted": stats["total_releases"],
                "providers_reset": len(stats["providers"]),
            }

        except Exception as e:
            logger.error(f"Error during cache purge: {e}", exc_info=True)
            raise


class ProviderSyncService:
    """
    Background sync service for fetching latest releases from providers.

    Runs periodic RSS-mode searches against configured search providers
    to populate the local cache with recent releases.
    """

    def __init__(self, cache_service: ProviderCacheService, search_providers: List[Any]):
        """
        Initialize provider sync service.

        Args:
            cache_service: ProviderCacheService instance
            search_providers: List of search provider instances
        """
        self.cache_service = cache_service
        self.search_providers = search_providers

        logger.info(f"Provider sync initialized with {len(search_providers)} providers")

    async def sync_all_providers(self):
        """
        Sync all configured providers.

        This is the main entrypoint for background sync task.
        Handles initial sync and incremental sync automatically.

        Returns:
            Dictionary with sync statistics
        """
        logger.info("Starting provider sync for all providers")
        start_time = time.time()

        synced_count = 0
        failed_count = 0
        total_added = 0
        total_nzbs_downloaded = 0

        for provider in self.search_providers:
            try:
                # Check sync status
                session = self.cache_service._session_factory()
                try:
                    sync_status = session.query(SyncStatus).filter(SyncStatus.provider_name == provider.name).first()

                    provider_added = 0
                    if not sync_status:
                        # First sync for this provider
                        logger.info(f"Running initial sync for provider: {provider.name}")
                        provider_added = await self._initial_sync(provider, session)
                    elif not sync_status.initial_sync_completed:
                        # Initial sync not completed yet
                        logger.info(f"Completing initial sync for provider: {provider.name}")
                        provider_added = await self._initial_sync(provider, session)
                    else:
                        # Incremental sync
                        logger.debug(f"Running incremental sync for provider: {provider.name}")
                        provider_added = await self._incremental_sync(provider, session)

                    total_added += provider_added
                    synced_count += 1
                finally:
                    session.close()

            except Exception as e:
                logger.error(f"Sync failed for provider {provider.name}: {e}", exc_info=True)
                failed_count += 1
                # Continue with next provider

        duration = time.time() - start_time
        logger.info(
            f"Provider sync complete: {synced_count} succeeded, {failed_count} failed, "
            f"{total_added} releases added, duration: {duration:.1f}s"
        )

        return {
            "synced_count": synced_count,
            "failed_count": failed_count,
            "total_added": total_added,
            "total_nzbs_downloaded": total_nzbs_downloaded,
            "duration_seconds": duration,
        }

    async def _initial_sync(self, provider: Any, session: Session) -> int:
        """
        Perform initial sync for a provider.

        Fetches the most recent releases using RSS mode.

        Args:
            provider: Search provider instance
            session: Database session

        Returns:
            Number of releases added
        """
        sync_start = time.time()

        try:
            # Fetch releases using RSS mode (empty query)
            logger.info(f"Fetching initial {INITIAL_SYNC_LIMIT} releases from {provider.name}")
            results = provider.search(query="", category=None)  # RSS mode

            if not results:
                logger.warning(f"No results from initial sync for {provider.name}")
                return 0

            # Limit to initial sync limit
            results = results[:INITIAL_SYNC_LIMIT]

            # Convert to cache format and upsert
            cache_releases = self._convert_results_to_cache_format(results, provider)
            added_count = self.cache_service.upsert_releases(cache_releases)

            # Update sync status
            sync_status = session.query(SyncStatus).filter(SyncStatus.provider_name == provider.name).first()

            if not sync_status:
                sync_status = SyncStatus(
                    provider_name=provider.name,
                    total_syncs=0,
                    failed_syncs=0,
                    total_releases_cached=0,
                    last_sync_added=0,
                )
                session.add(sync_status)
                session.flush()  # Ensure defaults are set

            sync_status.last_sync_time = utc_now()
            sync_status.last_successful_sync = utc_now()
            sync_status.total_syncs = (sync_status.total_syncs or 0) + 1
            sync_status.last_sync_added = added_count
            sync_status.last_sync_duration_seconds = time.time() - sync_start
            sync_status.initial_sync_completed = True

            # Set marker to first result GUID for incremental sync
            if results:
                sync_status.last_sync_release_guid = self._get_guid_from_result(results[0])

            # Update release count
            total_cached = session.query(CachedRelease).filter(CachedRelease.provider_name == provider.name).count()
            sync_status.total_releases_cached = total_cached

            session.commit()

            logger.info(
                f"Initial sync complete for {provider.name}: "
                f"{added_count} releases added, {len(results)} total fetched"
            )

            return added_count

        except Exception as e:
            session.rollback()
            logger.error(f"Initial sync failed for {provider.name}: {e}", exc_info=True)

            # Update sync status with failure
            sync_status = session.query(SyncStatus).filter(SyncStatus.provider_name == provider.name).first()
            if sync_status:
                sync_status.last_sync_time = utc_now()
                sync_status.total_syncs = (sync_status.total_syncs or 0) + 1
                sync_status.failed_syncs = (sync_status.failed_syncs or 0) + 1
                session.commit()

            return 0

    async def _incremental_sync(self, provider: Any, session: Session) -> int:
        """
        Perform incremental sync for a provider.

        Fetches latest releases and stops when we hit the marker from last sync.

        Args:
            provider: Search provider instance
            session: Database session

        Returns:
            Number of releases added
        """
        sync_start = time.time()

        try:
            sync_status = session.query(SyncStatus).filter(SyncStatus.provider_name == provider.name).first()
            if not sync_status:
                logger.warning(f"No sync status for {provider.name}, running initial sync")
                await self._initial_sync(provider, session)
                return

            # Fetch latest releases using RSS mode
            logger.debug(f"Fetching latest {INCREMENTAL_SYNC_LIMIT} releases from {provider.name}")
            # Run blocking search in thread pool
            results = await run_in_thread(lambda: provider.search(query="", category=None))

            if not results:
                logger.debug(f"No new results from {provider.name}")
                # Update sync status even if no new results
                sync_status.last_sync_time = utc_now()
                sync_status.last_successful_sync = utc_now()
                sync_status.total_syncs = (sync_status.total_syncs or 0) + 1
                sync_status.last_sync_added = 0
                sync_status.last_sync_duration_seconds = time.time() - sync_start
                session.commit()
                return 0

            # Find where to stop (at marker GUID)
            marker_guid = sync_status.last_sync_release_guid
            new_results = []

            for result in results[:INCREMENTAL_SYNC_LIMIT]:
                result_guid = self._get_guid_from_result(result)
                if result_guid == marker_guid:
                    # Found marker - stop here
                    logger.debug(f"Hit sync marker for {provider.name}, stopping")
                    break
                new_results.append(result)

            if not new_results:
                logger.debug(f"No new releases for {provider.name}")
                # Update sync status even if no new results
                sync_status.last_sync_time = utc_now()
                sync_status.last_successful_sync = utc_now()
                sync_status.total_syncs = (sync_status.total_syncs or 0) + 1
                sync_status.last_sync_added = 0
                sync_status.last_sync_duration_seconds = time.time() - sync_start
                session.commit()
                return 0

            # Convert and upsert new releases
            cache_releases = self._convert_results_to_cache_format(new_results, provider)
            added_count = self.cache_service.upsert_releases(cache_releases)

            # Update sync status
            sync_status.last_sync_time = utc_now()
            sync_status.last_successful_sync = utc_now()
            sync_status.total_syncs = (sync_status.total_syncs or 0) + 1
            sync_status.last_sync_added = added_count
            sync_status.last_sync_duration_seconds = time.time() - sync_start

            # Update marker to first result GUID
            if results:
                sync_status.last_sync_release_guid = self._get_guid_from_result(results[0])

            # Update release count
            total_cached = session.query(CachedRelease).filter(CachedRelease.provider_name == provider.name).count()
            sync_status.total_releases_cached = total_cached

            session.commit()

            logger.info(
                f"Incremental sync complete for {provider.name}: "
                f"{added_count} new releases, {len(new_results)} fetched"
            )

            return added_count

        except Exception as e:
            session.rollback()
            logger.error(f"Incremental sync failed for {provider.name}: {e}", exc_info=True)

            # Update sync status with failure
            if sync_status:
                sync_status.last_sync_time = utc_now()
                sync_status.total_syncs = (sync_status.total_syncs or 0) + 1
                sync_status.failed_syncs = (sync_status.failed_syncs or 0) + 1
                session.commit()

            return 0

    def _convert_results_to_cache_format(self, results: List[Any], provider: Any) -> List[Dict[str, Any]]:
        """
        Convert search results to cache format.

        Args:
            results: List of SearchResult objects
            provider: Provider instance

        Returns:
            List of release dictionaries for caching
        """
        cache_releases = []

        for result in results:
            # Extract GUID (try multiple fields)
            guid = self._get_guid_from_result(result)
            if not guid:
                logger.warning(f"Skipping result without GUID: {result.title}")
                continue

            # Parse upload_date if available
            upload_date = self._parse_upload_date(result)

            cache_release = {
                "guid": guid,
                "title": result.title,
                "provider_name": provider.name,
                "provider_type": provider.type,
                "url": result.url,
                "download_url": result.url,
                "publication_date": result.publication_date,
                "upload_date": upload_date,
                "size_bytes": result.raw_metadata.get("size") if result.raw_metadata else None,
                "category": result.raw_metadata.get("category") if result.raw_metadata else None,
                "language": None,  # Could be extracted from raw_metadata if available
                "country": None,
                "fuzzy_match_group": None,  # Could implement fuzzy matching here
                "raw_metadata": result.raw_metadata if result.raw_metadata else {},
            }

            cache_releases.append(cache_release)

        return cache_releases

    def _get_guid_from_result(self, result: Any) -> Optional[str]:
        """
        Extract GUID from search result.

        Tries multiple fields: guid, id, url

        Args:
            result: SearchResult object

        Returns:
            GUID string or None
        """
        # Try raw_metadata first
        if result.raw_metadata:
            guid = result.raw_metadata.get("guid") or result.raw_metadata.get("id")
            if guid:
                return str(guid)

        # Fall back to URL as GUID
        if result.url:
            return result.url

        return None

    def _parse_upload_date(self, result: Any) -> Optional[datetime]:
        """
        Parse upload_date from search result.

        Tries multiple date formats from raw_metadata.

        Args:
            result: SearchResult object

        Returns:
            Parsed datetime or None
        """
        if not result.raw_metadata:
            return None

        # Try to get upload_date from raw_metadata
        upload_date_str = result.raw_metadata.get("upload_date") or result.raw_metadata.get("pubDate")
        if not upload_date_str:
            return None

        # Try parsing with multiple formats
        for date_format in UPLOAD_DATE_FORMATS:
            try:
                return datetime.strptime(upload_date_str, date_format)
            except (ValueError, TypeError):
                continue

        logger.debug(f"Failed to parse upload_date: {upload_date_str}")
        return None
