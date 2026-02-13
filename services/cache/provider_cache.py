"""
NZB content cache service.

Caches NZB file content fetched from providers to avoid repeated
provider hits on download submissions and retries. Stores NZB XML
in a local SQLite database keyed by download URL.
"""

import logging
import os
from typing import Dict, Optional

import requests
from sqlalchemy import create_engine, func, text
from sqlalchemy.orm import sessionmaker

from core.constants.cache import DEFAULT_MAX_NZB_FETCHES_PER_HOUR
from core.parsers import utc_now
from core.utils.rate_limiter import ProviderRateLimiter
from models.cache import CacheBase, NzbCache

logger = logging.getLogger(__name__)


class NzbCacheService:
    """
    Caches NZB file content to avoid provider rate limits.

    When a download is submitted, the NZB XML is fetched once from
    the provider and stored locally. Subsequent submissions (retries,
    re-downloads) use the cached content directly — the provider is
    never hit again for the same URL.
    """

    def __init__(
        self,
        cache_db_path: str,
        max_nzb_fetches_per_hour: int = DEFAULT_MAX_NZB_FETCHES_PER_HOUR,
        session_factory=None,
    ):
        """
        Initialize NZB cache service.

        Args:
            cache_db_path: Path to cache SQLite database
            max_nzb_fetches_per_hour: Max NZB fetches per hour (0 = unlimited)
            session_factory: Optional pre-built sessionmaker for shared engine usage.
                             If not provided, creates its own engine (backward compatible).
        """
        self.cache_db_path = cache_db_path
        self._nzb_rate_limiter = ProviderRateLimiter(max_requests=max_nzb_fetches_per_hour)

        # Ensure cache directory exists
        cache_dir = os.path.dirname(cache_db_path)
        os.makedirs(cache_dir, exist_ok=True)

        if session_factory is not None:
            # Use shared engine/session factory (preferred — avoids duplicate connections)
            self._session_factory = session_factory
            self._engine = None
        else:
            # Create own engine (backward compatible for tests and standalone usage)
            db_url = f"sqlite:///{cache_db_path}"
            self._engine = create_engine(db_url, echo=False)
            self._session_factory = sessionmaker(bind=self._engine)
            CacheBase.metadata.create_all(self._engine)

        # Drop legacy tables from the old search cache system
        self._drop_legacy_tables()

        logger.info(f"NZB cache initialized: {cache_db_path}")

    def _drop_legacy_tables(self):
        """Drop tables from old cache systems that are no longer needed."""
        legacy_tables = ["cached_releases", "cached_releases_fts", "sync_status", "rss_cache"]
        legacy_triggers = [
            "cached_releases_fts_insert",
            "cached_releases_fts_delete",
            "cached_releases_fts_update",
        ]

        # Get engine — either our own or extract from session factory binding
        engine = self._engine
        if engine is None:
            try:
                engine = self._session_factory.kw["bind"]
            except (AttributeError, KeyError):
                logger.debug("Cannot drop legacy tables: no engine available")
                return

        with engine.connect() as conn:
            for trigger in legacy_triggers:
                try:
                    conn.execute(text(f"DROP TRIGGER IF EXISTS {trigger}"))
                except Exception:
                    pass

            for table in legacy_tables:
                try:
                    conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
                except Exception:
                    pass
            conn.commit()

    def get_nzb_content(self, download_url: str) -> Optional[str]:
        """
        Get NZB content for a URL, fetching from provider if not cached.

        Tries in order:
        1. Return cached content if available (no provider hit)
        2. Fetch from provider, cache it, return it (one provider hit)
        3. Return None if rate limited or fetch fails

        Args:
            download_url: NZB download URL (may be a Prowlarr proxy URL)

        Returns:
            NZB XML content as string, or None if unavailable
        """
        session = self._session_factory()
        try:
            # Check cache first
            cached = session.query(NzbCache).filter(NzbCache.download_url == download_url).first()
            if cached:
                logger.debug(f"NZB cache hit for {download_url[:80]}")
                return cached.nzb_content

            # Rate limit provider fetches
            if not self._nzb_rate_limiter.acquire("nzb_fetch"):
                wait = self._nzb_rate_limiter.wait_time("nzb_fetch")
                logger.warning(f"NZB fetch rate limited, next slot in {wait:.0f}s")
                return None

            # Fetch from provider and cache
            logger.info(f"Fetching NZB from provider: {download_url[:80]}")
            try:
                response = requests.get(download_url, timeout=30)
                response.raise_for_status()
                nzb_content = response.text

                if not nzb_content or "<nzb" not in nzb_content.lower():
                    logger.warning(f"Response does not appear to be valid NZB XML (length: {len(nzb_content or '')})")

                # Cache it (even if invalid — prevents repeated fetches)
                entry = NzbCache(
                    download_url=download_url,
                    nzb_content=nzb_content,
                    cached_at=utc_now(),
                )
                session.add(entry)
                session.commit()

                logger.info(f"Cached NZB content ({len(nzb_content)} bytes)")
                return nzb_content

            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to fetch NZB from {download_url[:80]}: {e}", exc_info=True)
                return None

        finally:
            session.close()

    def get_stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        session = self._session_factory()
        try:
            total = session.query(func.count(NzbCache.id)).scalar() or 0  # pylint: disable=not-callable
            return {"total_cached_nzbs": total}
        finally:
            session.close()

    def purge_all(self) -> Dict[str, int]:
        """Delete all cached NZB content."""
        session = self._session_factory()
        try:
            count = session.query(NzbCache).delete()
            session.commit()
            logger.info(f"Purged {count} cached NZBs")
            return {"deleted": count}
        finally:
            session.close()
