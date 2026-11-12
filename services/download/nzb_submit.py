"""
Shared NZB submission helper.

Centralises the cache-first NZB content submission logic used by both
DownloadManager and QueueProcessor, preventing duplication.
"""

import logging
from typing import Optional
from urllib.parse import urlsplit

from core.interfaces import DownloadClient
from services.cache.provider_cache import NzbContentRejected

logger = logging.getLogger(__name__)

# NZB XML caching is for Usenet. newsnab and rss produce NZBs; torznab does not.
_NZB_PROVIDERS = frozenset({"newsnab", "rss"})
_NON_NZB_PROVIDERS = frozenset({"torznab", "internet_archive"})
_USENET_CLIENT_TYPES = frozenset({"sabnzbd", "nzbget"})
_TORRENT_CLIENT_TYPES = frozenset({"qbittorrent"})
_USENET_CLIENT_CLASSES = frozenset({"SABnzbdClient", "NZBGetClient"})


def _client_type(client) -> str:
    """Configured client type, lowercased. Missing config is an empty string."""
    return str(getattr(client, "type", "") or "").lower()


def _is_torrent_client(client) -> bool:
    """qBittorrent uploads .torrent bytes. That override is not an NZB upload."""
    if _client_type(client) in _TORRENT_CLIENT_TYPES:
        return True
    return type(client).__name__ == "QBittorrentClient"


def _is_usenet_client(client) -> bool:
    """SABnzbd and NZBGet accept NZB XML directly."""
    if _client_type(client) in _USENET_CLIENT_TYPES:
        return True
    return type(client).__name__ in _USENET_CLIENT_CLASSES


def _is_torrent_url(url: str) -> bool:
    """Magnet links and .torrent enclosures are not NZB documents."""
    if not url:
        return False
    lowered = url.strip().lower()
    if lowered.startswith("magnet:"):
        return True
    return urlsplit(lowered).path.endswith(".torrent")


def _should_use_nzb_cache(client, url: str, provider: Optional[str]) -> bool:
    """
    Use the NZB cache only for Usenet clients and newsnab/rss providers.

    qBittorrent implements submit_content for .torrent files. Routing a Torznab
    enclosure through the NZB cache rejects it (the body is not NZB XML) and the
    grab never reaches the client.
    """
    provider_name = (provider or "").strip().lower()
    if provider_name in _NON_NZB_PROVIDERS or _is_torrent_client(client) or _is_torrent_url(url):
        return False
    if provider_name and provider_name not in _NZB_PROVIDERS and not _is_usenet_client(client):
        return False
    return type(client).submit_content is not DownloadClient.submit_content


def submit_with_nzb_content(
    client: DownloadClient,
    nzb_url: str,
    title: str,
    category: Optional[str] = None,
    nzb_cache_service=None,
    provider: Optional[str] = None,
) -> Optional[str]:
    """
    Submit a download, preferring cached NZB content over URL to avoid provider rate limits.

    Tries in order:
    1. Cached NZB content from provider cache → submit_content() (no provider hit)
    2. Fallback to URL submission → submit() (provider hit by download client)

    Torrent clients and Torznab/.torrent URLs skip step 1. The cache only stores
    NZB XML, and a torrent enclosure is not an NZB.

    Args:
        client: Download client to submit to
        nzb_url: NZB download URL, or a torrent/magnet URL
        title: Download title
        category: Optional download category
        nzb_cache_service: Optional NZB cache service; if None, skips cache step
        provider: Provider type (newsnab, rss, torznab, ...). Empty when unknown.

    Returns:
        Job ID from download client, or None if all methods failed

    Raises:
        NzbContentRejected: The indexer returned a non-NZB body. The URL is not
            submitted, because the download client would fetch the same body.
    """
    if nzb_cache_service and _should_use_nzb_cache(client, nzb_url, provider):
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
        except NzbContentRejected:
            raise
        except Exception as e:
            logger.warning(f"NZB content submission error: {e}, falling back to URL")

    return client.submit(url=nzb_url, title=title, category=category)
