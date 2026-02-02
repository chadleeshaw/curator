"""
Provider cache service for caching search provider results.

Manages cached releases from search providers with FTS5 full-text search
for fast local searching without hitting provider APIs.
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests
from sqlalchemy import create_engine, func, text
from sqlalchemy.orm import sessionmaker

from core.constants.cache import (
    CACHE_CLEANUP_BATCH_SIZE,
    CACHE_RETENTION_DAYS,
    FTS5_TOKENIZER,
    FUZZY_MATCH_SIMILARITY_THRESHOLD,
)
from core.parsers import utc_now
from core.parsers.title import TitleMatcher
from models.cache import CacheBase, CachedRelease, SyncStatus

from .utils import escape_fts_query

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

        # Run schema migrations (drop deprecated columns)
        self._migrate_schema()

        logger.info(f"Provider cache initialized: {cache_db_path}")

    def _migrate_schema(self):
        """Run schema migrations to remove deprecated columns"""
        # Deprecated columns to remove (from old NZB file caching feature)
        deprecated_columns = ["has_nzb_file", "nzb_file_path", "nzb_downloaded_at", "nzb_file_size"]

        with self._engine.connect() as conn:
            # Get current columns in cached_releases table
            result = conn.execute(text("PRAGMA table_info(cached_releases)"))
            existing_columns = {row[1] for row in result.fetchall()}

            # Get all indexes on cached_releases table
            result = conn.execute(text("PRAGMA index_list(cached_releases)"))
            indexes = [(row[1], row[2]) for row in result.fetchall()]  # (name, unique)

            for column_name in deprecated_columns:
                if column_name in existing_columns:
                    logger.info(f"Removing deprecated column 'cached_releases.{column_name}'")
                    try:
                        # First, drop any indexes that reference this column
                        for index_name, _ in indexes:
                            # Check if this index is for the column being dropped
                            if column_name in index_name:
                                try:
                                    conn.execute(text(f"DROP INDEX IF EXISTS {index_name}"))
                                    conn.commit()
                                    logger.debug(f"Dropped index {index_name}")
                                except Exception:
                                    pass  # Index might not exist

                        conn.execute(text(f"ALTER TABLE cached_releases DROP COLUMN {column_name}"))
                        conn.commit()
                        logger.info(f"Removed column cached_releases.{column_name}")
                    except Exception as e:
                        # SQLite < 3.35.0 doesn't support DROP COLUMN, log warning but continue
                        logger.warning(
                            f"Could not remove column cached_releases.{column_name}: {e}. "
                            f"This column is deprecated and can be safely ignored."
                        )

    def _initialize_database(self):
        """Create database tables, compound indexes, and FTS5 virtual table for full-text search"""
        # Create all tables
        CacheBase.metadata.create_all(self._engine)

        # Create FTS5 virtual table and compound indexes for full-text search
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

            # Create compound indexes for common filter combinations (if they don't exist)
            # These dramatically speed up filtered searches
            try:
                conn.execute(
                    text(
                        """
                        CREATE INDEX IF NOT EXISTS idx_category_language_date
                        ON cached_releases(category, language, upload_date DESC)
                        """
                    )
                )
                conn.execute(
                    text(
                        """
                        CREATE INDEX IF NOT EXISTS idx_fuzzy_group_date
                        ON cached_releases(fuzzy_match_group, upload_date DESC)
                        """
                    )
                )
                conn.execute(
                    text(
                        """
                        CREATE INDEX IF NOT EXISTS idx_normalized_title_date
                        ON cached_releases(normalized_title, upload_date DESC)
                        """
                    )
                )
                conn.commit()
                logger.info("Created compound indexes for optimized filtering")
            except Exception as e:
                logger.debug(f"Compound indexes may already exist: {e}")

    def search(
        self,
        query: str,
        category: Optional[str] = None,
        language: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        deduplicate: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Search cached releases using FTS5 full-text search with optional pagination and deduplication.

        Args:
            query: Search query
            category: Optional category filter
            language: Optional language filter
            limit: Maximum number of results (default: 50)
            offset: Offset for pagination (default: 0)
            deduplicate: Use SQL-based deduplication to return best match per fuzzy group (default: True)

        Returns:
            List of matching releases as dictionaries
        """
        # Escape the query for safe FTS5 MATCH usage
        fts_query = escape_fts_query(query)

        session = self._session_factory()
        try:
            if deduplicate:
                # Use SQL window function for efficient deduplication at database level
                # This selects the best (most recent) release per fuzzy_match_group
                subquery = text(
                    """
                    SELECT cr.*,
                           ROW_NUMBER() OVER (
                               PARTITION BY cr.fuzzy_match_group
                               ORDER BY cr.upload_date DESC, cr.last_seen DESC
                           ) as rn
                    FROM cached_releases cr
                    INNER JOIN cached_releases_fts fts ON cr.id = fts.rowid
                    WHERE cached_releases_fts MATCH :fts_query
                    """
                )

                params = {"fts_query": fts_query}

                # Add filters to subquery
                if category:
                    subquery = text(str(subquery).replace("WHERE", "WHERE cr.category = :category AND"))
                    params["category"] = category

                if language:
                    subquery = text(str(subquery).replace("WHERE", "WHERE cr.language = :language AND"))
                    params["language"] = language

                # Wrap in outer query to filter by row number and apply pagination
                final_query = text(
                    f"""
                    SELECT * FROM ({subquery})
                    WHERE rn = 1
                    ORDER BY upload_date DESC, last_seen DESC
                    LIMIT :limit OFFSET :offset
                    """
                )
                params["limit"] = limit
                params["offset"] = offset

                result = session.execute(final_query, params)
                # Convert rows directly to dicts to avoid extra queries
                columns = result.keys()
                releases = [dict(zip(columns, row)) for row in result.fetchall()]

            else:
                # No deduplication - use simple ORM query with join
                query_obj = (
                    session.query(CachedRelease)
                    .join(
                        text("cached_releases_fts ON cached_releases.id = cached_releases_fts.rowid"),
                        isouter=False,
                    )
                    .filter(text("cached_releases_fts MATCH :fts_query"))
                    .params(fts_query=fts_query)
                )

                # Add category filter if specified
                if category:
                    query_obj = query_obj.filter(CachedRelease.category == category)

                # Add language filter if specified
                if language:
                    query_obj = query_obj.filter(CachedRelease.language == language)

                # Order by upload_date (newest first), then last_seen, with pagination
                query_obj = (
                    query_obj.order_by(CachedRelease.upload_date.desc(), CachedRelease.last_seen.desc())
                    .limit(limit)
                    .offset(offset)
                )

                # Execute single optimized query and convert to dicts
                releases = [release.to_dict() for release in query_obj.all()]

            logger.info(
                f"Cache search: found {len(releases)} results for query '{query}' "
                f"(offset={offset}, limit={limit}, dedupe={deduplicate})"
            )
            return releases

        finally:
            session.close()

    def count(
        self,
        query: str,
        category: Optional[str] = None,
        language: Optional[str] = None,
        deduplicate: bool = True,
    ) -> int:
        """
        Get total count of matching releases for pagination.

        Args:
            query: Search query
            category: Optional category filter
            language: Optional language filter
            deduplicate: Count deduplicated results (default: True)

        Returns:
            Total count of matching releases
        """
        # Escape the query for safe FTS5 MATCH usage
        fts_query = escape_fts_query(query)

        session = self._session_factory()
        try:
            if deduplicate:
                # Count distinct fuzzy_match_groups
                sql_query = text(
                    """
                    SELECT COUNT(DISTINCT cr.fuzzy_match_group)
                    FROM cached_releases cr
                    INNER JOIN cached_releases_fts fts ON cr.id = fts.rowid
                    WHERE cached_releases_fts MATCH :fts_query
                    """
                )
            else:
                # Count all matching releases
                sql_query = text(
                    """
                    SELECT COUNT(*)
                    FROM cached_releases cr
                    INNER JOIN cached_releases_fts fts ON cr.id = fts.rowid
                    WHERE cached_releases_fts MATCH :fts_query
                    """
                )

            params = {"fts_query": fts_query}

            # Add filters
            if category:
                sql_query = text(str(sql_query).replace("WHERE", "WHERE cr.category = :category AND"))
                params["category"] = category

            if language:
                sql_query = text(str(sql_query).replace("WHERE", "WHERE cr.language = :language AND"))
                params["language"] = language

            result = session.execute(sql_query, params)
            return result.scalar()

        finally:
            session.close()

    async def resolve_redirect_url(self, url: str, max_redirects: int = 10) -> str:
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
            >>> await service.resolve_redirect_url(proxy_url)
            "https://api.nzb.su/getnzb/abc123.nzb&i=..."
        """

        def _resolve():
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

                # Return final URL and whether redirect occurred
                return (final_url, final_url != url)

            except requests.exceptions.TooManyRedirects:
                logger.warning(f"Too many redirects resolving URL (>{max_redirects}), using original")
                return (url, False)
            except requests.exceptions.RequestException as e:
                logger.warning(f"Failed to resolve URL redirect: {e}, using original URL")
                return (url, False)
            except Exception as e:
                logger.error(f"Unexpected error resolving URL: {e}", exc_info=True)
                return (url, False)

        # Run in thread pool to avoid blocking async event loop
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _resolve)

    async def upsert_releases(self, releases: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        Insert or update releases in cache.

        Handles deduplication by GUID. If a release with the same GUID exists:
        - If new upload_date is newer, replace the entire record
        - Otherwise, just update last_seen timestamp

        Args:
            releases: List of release dictionaries from providers

        Returns:
            Dictionary with counts: {'added': int, 'updated': int, 'redirects_resolved': int}
        """
        session = self._session_factory()
        try:
            added_count = 0
            updated_count = 0
            redirects_resolved = 0

            # Phase 1: Resolve all URLs in parallel (fast!)
            logger.debug(f"Resolving {len(releases)} proxy URLs in parallel...")
            url_tasks = []
            for release_data in releases:
                download_url = release_data.get("download_url", release_data.get("url", ""))
                url_tasks.append(self.resolve_redirect_url(download_url))

            # Resolve all URLs concurrently
            resolved_urls = await asyncio.gather(*url_tasks)

            # Phase 2: Database operations (sequential with resolved URLs)
            for release_data, (resolved_url, was_redirected) in zip(releases, resolved_urls):
                guid = release_data.get("guid")
                if not guid:
                    logger.warning("Skipping release without GUID")
                    continue

                if was_redirected:
                    redirects_resolved += 1

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

                        # Create new record with already-resolved URL
                        new_release = self._create_release_from_data(release_data, resolved_url)
                        session.add(new_release)
                        added_count += 1
                    else:
                        # Same or older upload - just update last_seen
                        existing.last_seen = utc_now()
                        updated_count += 1
                else:
                    # New release - add to cache with already-resolved URL
                    new_release = self._create_release_from_data(release_data, resolved_url)
                    session.add(new_release)
                    added_count += 1

            session.commit()

            # Log summary if any redirects were resolved
            if redirects_resolved > 0:
                logger.info(f"Resolved {redirects_resolved} proxy URL redirects during cache update")

            logger.debug(f"Upserted {added_count} new releases, updated {updated_count} existing releases")
            return {
                "added": added_count,
                "updated": updated_count,
                "redirects_resolved": redirects_resolved,
            }

        except Exception as e:
            session.rollback()
            logger.error(f"Error upserting releases: {e}", exc_info=True)
            raise
        finally:
            session.close()

    def _create_release_from_data(self, release_data: Dict[str, Any], resolved_url: str) -> CachedRelease:
        """
        Create CachedRelease model from dictionary with pre-resolved URL.

        Args:
            release_data: Release data from provider
            resolved_url: Already-resolved download URL

        Returns:
            CachedRelease model instance
        """
        # Normalize title for better matching
        title = release_data.get("title", "")
        title_matcher = TitleMatcher()
        normalized_title = title_matcher.clean_release_title(title).lower()

        return CachedRelease(
            guid=release_data.get("guid"),
            title=title,
            normalized_title=normalized_title,
            provider_name=release_data.get("provider_name"),
            provider_type=release_data.get("provider_type"),
            download_url=resolved_url,
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

            # Fallback: if no sync status but we have releases, use the newest release date
            # This handles cases where releases exist but sync tracking wasn't set up
            if last_sync is None and newest is not None:
                last_sync = newest

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
                f"Cache purge complete: "
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
