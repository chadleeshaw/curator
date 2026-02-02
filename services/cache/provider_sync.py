"""
Provider sync service for background synchronization with search providers.

Runs periodic RSS-mode searches against configured search providers
to populate the local cache with recent releases.
"""

import logging
import time
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from core.constants.cache import (
    INCREMENTAL_SYNC_LIMIT,
    INITIAL_SYNC_LIMIT,
)
from core.parsers import utc_now
from core.utils import run_in_thread
from models.cache import CachedRelease, SyncStatus

from .provider_cache import ProviderCacheService
from .utils import parse_upload_date

logger = logging.getLogger(__name__)


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
            # Run in thread pool to avoid blocking event loop
            logger.info(f"Fetching initial {INITIAL_SYNC_LIMIT} releases from {provider.name}")
            results = await run_in_thread(lambda: provider.search(query="", category=None))

            if not results:
                logger.warning(f"No results from initial sync for {provider.name}")
                return 0

            # Limit to initial sync limit
            results = results[:INITIAL_SYNC_LIMIT]

            # Convert to cache format and upsert
            cache_releases = self._convert_results_to_cache_format(results, provider)
            upsert_stats = await self.cache_service.upsert_releases(cache_releases)
            added_count = upsert_stats["added"] + upsert_stats["updated"]

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
                return 0

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
            upsert_stats = await self.cache_service.upsert_releases(cache_releases)
            added_count = upsert_stats["added"] + upsert_stats["updated"]

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
            upload_date = parse_upload_date(result)

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
