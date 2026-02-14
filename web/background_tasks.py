"""
Background task definitions for the Curator application.

This module contains all periodic background tasks that are scheduled
by the TaskScheduler. Each task is defined as an async function that
performs a specific maintenance or processing operation.
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from core.parsers import utc_now
from core import constants

if TYPE_CHECKING:
    from web.app import AppState

logger = logging.getLogger(__name__)


async def feed_sync_task(app_state: "AppState") -> None:
    """Sync RSS feeds from all providers into the local entry cache."""

    def _run_feed_sync():
        if not app_state.feed_sync_service or not app_state.search_providers:
            return

        logger.debug("Feed sync: Starting RSS feed sync")

        stats = app_state.feed_sync_service.sync_all_providers(app_state.search_providers)

        if stats["total_new"] > 0:
            logger.info(
                f"Feed sync: {stats['total_new']} new entries, "
                f"{stats['total_updated']} updated across "
                f"{stats['providers_synced']} providers"
            )

        app_state.feed_sync_service.expire_old_entries()

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _run_feed_sync)
    except Exception as e:
        logger.error(f"Feed sync error: {e}", exc_info=True)


async def auto_download_task(app_state: "AppState") -> None:
    """Cache-first adaptive search and download for tracked periodicals."""
    logger.info("Starting auto-download task")

    def _run_auto_download():
        db_session = app_state.session_factory()
        try:
            if not app_state.download_manager:
                return

            logger.debug("Auto-download: Starting Issue Discovery & Tracking run")

            # Phase 1.5: Cache-first local matching (zero API calls)
            cache_match_new = _process_cache_matches(app_state, db_session)

            # Phase 2: Adaptive per-periodical API search
            _process_periodical_searches(app_state, db_session)

            # Phase 3: Download from priority queue
            logger.debug("Auto-download: Checking download queue")
            app_state.download_manager.submit_discovered_batch(db_session, app_state.issue_discovery_service)

            # Phase 4: Cleanup stale search results
            _cleanup_stale_search_results(app_state, db_session)

            logger.debug("Auto-download: Completed run")
        finally:
            db_session.close()

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _run_auto_download)
    except Exception as e:
        logger.error(f"Auto-download error: {e}", exc_info=True)


def _process_cache_matches(app_state: "AppState", db_session) -> int:
    """Process cached feed entries and match against tracked periodicals.

    Returns:
        Number of new issues discovered from cache matching
    """
    cache_match_new = 0

    if not app_state.feed_sync_service or not app_state.feed_match_service:
        return cache_match_new

    batch_size = app_state.tasks_config.get("feed_sync_match_batch_size", constants.FEED_SYNC_MATCH_BATCH_SIZE)
    new_entries = app_state.feed_sync_service.get_new_entries(limit=batch_size)

    if not new_entries:
        return cache_match_new

    logger.debug(f"Auto-download: Matching {len(new_entries)} cached feed entries")
    match_result = app_state.feed_match_service.match_entries_against_tracking(new_entries, db_session)

    for tracking_id, search_results in match_result["matches"].items():
        try:
            record_stats = app_state.issue_discovery_service.record_search_results(
                tracking_id, search_results, db_session
            )
            if record_stats["new"] > 0:
                cache_match_new += record_stats["new"]

            eval_stats = app_state.issue_discovery_service.evaluate_discovered_issues(tracking_id, db_session)
            if eval_stats["wanted"] > 0:
                logger.info(f"Auto-download: Cache match - {eval_stats['wanted']} wanted from tracking {tracking_id}")

            # Update last_cache_match timestamp if we found any results (new or updated)
            # This helps the adaptive scheduler avoid redundant API searches
            if record_stats["new"] > 0 or record_stats["updated"] > 0:
                from models.database import PeriodicalTracking

                tracking = db_session.query(PeriodicalTracking).filter_by(id=tracking_id).first()
                if tracking:
                    tracking.last_cache_match = utc_now()
                    db_session.commit()
                    logger.debug(f"Auto-download: Updated last_cache_match for tracking {tracking_id}")

        except Exception as e:
            logger.error(
                f"Auto-download: Error recording cache matches for tracking {tracking_id}: {e}",
                exc_info=True,
            )

    app_state.feed_sync_service.mark_entries_matched(match_result["matched_entry_ids"])
    app_state.feed_sync_service.mark_entries_skipped(match_result["skipped_entry_ids"])

    if cache_match_new > 0:
        logger.info(
            f"Auto-download: Cache-first matching found {cache_match_new} new issues "
            f"from {match_result['stats']['matched']} feed entries (zero API calls)"
        )

    return cache_match_new


def _process_periodical_searches(app_state: "AppState", db_session) -> None:
    """Search for issues of periodicals that need refresh per adaptive scheduler.

    Includes rate-limit-aware pacing: re-checks provider status after each search
    and stops early when all providers are exhausted, avoiding wasted iterations
    and unfair adaptive scheduler penalties.
    """
    periodicals_to_search = app_state.search_scheduler.select_periodicals_to_search(db_session)

    if not periodicals_to_search:
        logger.debug("Auto-download: No periodicals need searching at this time")
        return

    # Check if all providers are rate-limited before we even start
    if app_state.download_manager.all_providers_rate_limited:
        logger.info(
            "Auto-download: All search providers are rate limited, deferring %d periodical searches to next run",
            len(periodicals_to_search),
        )
        return

    # Get cache-aware search skip threshold from config (default: 1 hour)
    cache_skip_threshold_hours = app_state.tasks_config.get("cache_aware_search_skip_hours", 1)
    # Delay between per-periodical API searches (seconds) to pace requests
    inter_search_delay = app_state.tasks_config.get("inter_search_delay", 5)
    now = utc_now()

    searched_count = 0
    skipped_cache = 0

    for i, periodical in enumerate(periodicals_to_search):
        try:
            # Re-check rate limits before each search — providers may have become
            # rate-limited from the previous iteration's API calls
            if app_state.download_manager.all_providers_rate_limited:
                remaining = len(periodicals_to_search) - i
                logger.info(
                    "Auto-download: All providers hit rate limits after %d searches, "
                    "deferring %d remaining periodicals to next run",
                    searched_count,
                    remaining,
                )
                break

            # Cache-aware optimization: Skip API searches if cache matching found results recently
            # This prevents redundant API calls when the feed cache is already working
            if periodical.last_cache_match and cache_skip_threshold_hours > 0:
                # Normalize to naive UTC to avoid offset-naive vs offset-aware TypeError
                # (SQLite may return naive datetimes even for timezone-aware columns)
                now_naive = now.replace(tzinfo=None)
                cache_match_naive = periodical.last_cache_match.replace(tzinfo=None)
                time_since_cache_match = now_naive - cache_match_naive
                hours_since_cache_match = time_since_cache_match.total_seconds() / 3600

                if hours_since_cache_match < cache_skip_threshold_hours:
                    logger.info(
                        f"Auto-download: Skipping API search for '{periodical.title}' - "
                        f"cache matched {hours_since_cache_match:.1f}h ago "
                        f"(threshold: {cache_skip_threshold_hours}h)"
                    )
                    skipped_cache += 1
                    continue

            # Pace searches: add delay between API searches (skip delay for the first one)
            if searched_count > 0 and inter_search_delay > 0:
                logger.debug(f"Auto-download: Waiting {inter_search_delay}s before next search")
                time.sleep(inter_search_delay)

            aliases = _extract_search_aliases(periodical)

            logger.debug(f"Auto-download: Searching for '{periodical.title}'")
            search_results = app_state.download_manager.search_periodical_issues(
                periodical.title, db_session, aliases=aliases
            )
            searched_count += 1

            if not search_results:
                logger.debug(f"Auto-download: No results found for '{periodical.title}'")
                # Only penalize the adaptive scheduler if providers aren't all rate-limited
                # (if they are, the empty result is due to rate limiting, not a real empty search)
                if not app_state.download_manager.all_providers_rate_limited:
                    app_state.search_scheduler.update_search_stats(periodical.id, 0, db_session)
                continue

            logger.debug(f"Auto-download: Found {len(search_results)} results for '{periodical.title}'")

            record_stats = app_state.issue_discovery_service.record_search_results(
                periodical.id, search_results, db_session
            )

            if record_stats["new"] > 0:
                logger.info(f"Auto-download: '{periodical.title}' - {record_stats['new']} new issues")

            eval_stats = app_state.issue_discovery_service.evaluate_discovered_issues(periodical.id, db_session)
            if eval_stats["wanted"] > 0:
                logger.info(f"Auto-download: '{periodical.title}' - {eval_stats['wanted']} queued")

            app_state.search_scheduler.update_search_stats(periodical.id, record_stats["new"], db_session)

        except Exception as e:
            logger.error(
                f"Auto-download: Error processing '{periodical.title}': {e}",
                exc_info=True,
            )

    if searched_count > 0 or skipped_cache > 0:
        logger.info(f"Auto-download: Searched {searched_count} periodicals, " f"{skipped_cache} skipped (cache-fresh)")


def _extract_search_aliases(periodical) -> list:
    """Extract search aliases from tracking record."""
    if not periodical.search_aliases:
        return None

    aliases = [a.strip() for a in periodical.search_aliases.split(",") if a.strip()]
    if aliases:
        logger.debug(f"Auto-download: Searching '{periodical.title}' with {len(aliases)} aliases: {aliases}")
    return aliases if aliases else None


def _cleanup_stale_search_results(app_state: "AppState", db_session) -> None:
    """Remove search results older than retention period."""
    try:
        from datetime import timedelta

        from models.database import SearchResult as DBSearchResult

        retention_days = app_state.tasks_config.get(
            "search_result_retention_days", constants.SEARCH_RESULT_RETENTION_DAYS
        )
        cutoff = utc_now().replace(tzinfo=None) - timedelta(days=retention_days)
        deleted = (
            db_session.query(DBSearchResult)
            .filter(DBSearchResult.created_at < cutoff)
            .delete(synchronize_session=False)
        )
        db_session.commit()
        if deleted > 0:
            logger.info(f"Auto-download: Cleaned up {deleted} search results older than {retention_days} days")
    except Exception as e:
        logger.warning(f"Auto-download: Search result cleanup error: {e}")


async def download_monitoring_task(app_state: "AppState") -> None:
    """Monitor download client and scan downloads folder for files to import."""
    if not app_state.download_monitor_task:
        return

    try:
        interval = app_state.tasks_config.get("download_monitor_interval", constants.DOWNLOAD_MONITOR_INTERVAL)
        app_state.download_monitor_task.next_run_time = datetime.now() + timedelta(seconds=interval)
        await app_state.download_monitor_task.run()
    except Exception as e:
        logger.error(f"Download monitoring error: {e}", exc_info=True)


async def cleanup_orphaned_covers_task(app_state: "AppState") -> None:
    """Clean up cover files that aren't tied to any periodical."""
    await app_state.cover_cleanup_task.run()


async def ocr_processing_task(app_state: "AppState") -> None:
    """Process queued OCR jobs with process pool."""
    try:
        interval = app_state.tasks_config.get("ocr_processor_interval", constants.OCR_PROCESSOR_INTERVAL)
        app_state.ocr_processor_task.next_run_time = datetime.now() + timedelta(seconds=interval)

        stats = await app_state.ocr_processor_task.run()
        if stats.get("processed", 0) > 0:
            logger.info(f"OCR processor: {stats}")
    except Exception as e:
        logger.error(f"OCR processor error: {e}", exc_info=True)


async def folder_cleanup_periodic_task(app_state: "AppState") -> None:
    """Clean up empty folders and folders without importable files."""
    try:
        loop = asyncio.get_event_loop()
        stats = await loop.run_in_executor(None, app_state.folder_cleanup_task.run)
        if stats.get("total_deleted", 0) > 0:
            logger.info(f"Folder cleanup: {stats}")
    except Exception as e:
        logger.error(f"Folder cleanup error: {e}", exc_info=True)


async def auto_metadata_periodic_task(app_state: "AppState") -> None:
    """Backfill derived_metadata, sync issue_date, and queue missing OCR/text scans."""
    try:
        from core.utils import run_in_thread
        from services.auto_metadata import AutoMetadataService

        def _run_auto_metadata():
            service = AutoMetadataService(
                app_state.db_manager,
                library_base_dir=app_state.storage_config.get("library_dir"),
                category_prefix=app_state.category_prefix,
            )
            session = app_state.session_factory()
            try:
                return service.run_full_scan(session)
            finally:
                session.close()

        stats = await run_in_thread(_run_auto_metadata)
        logger.info(
            f"Auto-metadata: Processed {stats.get('total_periodicals', 0)} periodicals, "
            f"fixed {stats.get('paths_fixed', 0)} paths, "
            f"backfilled {stats.get('derived_metadata_backfilled', 0)} metadata, "
            f"synced {stats.get('issue_date_synced', 0)} dates, "
            f"queued {stats.get('ocr_queued', 0)} OCR, "
            f"queued {stats.get('text_scan_queued', 0)} text scans"
        )
    except Exception as e:
        logger.error(f"Auto-metadata error: {e}", exc_info=True)
