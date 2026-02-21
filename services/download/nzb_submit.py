"""
Shared NZB submission helper.

Centralises the cache-first NZB content submission logic used by both
DownloadManager and QueueProcessor, preventing duplication.
"""

import logging
from typing import Optional

from core.interfaces import DownloadClient

logger = logging.getLogger(__name__)


def submit_with_nzb_content(
    client: DownloadClient,
    nzb_url: str,
    title: str,
    category: Optional[str] = None,
    nzb_cache_service=None,
) -> Optional[str]:
    """
    Submit a download, preferring cached NZB content over URL to avoid provider rate limits.

    Tries in order:
    1. Cached NZB content from provider cache → submit_content() (no provider hit)
    2. Fallback to URL submission → submit() (provider hit by download client)

    Args:
        client: Download client to submit to
        nzb_url: NZB download URL
        title: Download title
        category: Optional download category
        nzb_cache_service: Optional NZB cache service; if None, skips cache step

    Returns:
        Job ID from download client, or None if all methods failed
    """
    if nzb_cache_service and type(client).submit_content is not DownloadClient.submit_content:
        try:
            nzb_content = nzb_cache_service.get_nzb_content(nzb_url)
            if nzb_content:
                job_id = client.submit_content(
                    nzb_content,
                    title=title,
                    category=category,
                )
                if job_id:
                    logger.info(f"Submitted via cached NZB content: {title} -> {job_id}")
                    return job_id
                logger.warning(f"submit_content failed for {title}, falling back to URL")
        except Exception as e:
            logger.warning(f"NZB content submission error: {e}, falling back to URL")

    return client.submit(url=nzb_url, title=title, category=category)
