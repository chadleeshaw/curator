"""
Shared helper functions used by multiple download coordinator classes.

Extracted to avoid code duplication across QueueCoordinator, SubmissionCoordinator,
and StatusCoordinator.
"""

import logging
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from core.interfaces import DownloadClient
from models.database import DownloadSubmission, PeriodicalTracking

logger = logging.getLogger(__name__)


def get_client_for_provider(
    download_clients: Dict[str, DownloadClient],
    provider_client_map: Dict[str, str],
    provider: str,
    url: Optional[str] = None,
) -> DownloadClient:
    """
    Get the appropriate download client for a provider.

    Uses URL-based fallback detection if provider routing fails.
    This handles legacy data where the provider field may be incorrect.

    Args:
        download_clients: Dict of available download clients keyed by type
        provider_client_map: Mapping of provider types to client types
        provider: Provider type (e.g., 'internet_archive', 'newsnab')
        url: Optional download URL for fallback provider detection

    Returns:
        DownloadClient instance for this provider
    """
    client_type = provider_client_map.get(provider, "default")

    # If routing failed (using default) and URL provided, try URL-based detection.
    if client_type == "default" and url:
        if "archive.org" in url or url.startswith("ia:"):
            if "internet_archive" in download_clients:
                logger.debug(
                    "Provider '%s' not in routing map, but URL indicates " "Internet Archive - using IA client",
                    provider,
                )
                client_type = "internet_archive"
            else:
                logger.warning("Archive.org URL detected but no IA client configured: %s", url)

    client = download_clients.get(client_type)
    if not client:
        logger.debug(
            "Client '%s' not found for provider '%s', using default",
            client_type,
            provider,
        )
        client = download_clients["default"]

    return client


def get_active_download_count(session: Session) -> int:
    """
    Count currently active (pending or downloading) submissions.

    Args:
        session: Database session

    Returns:
        Number of active downloads
    """
    return (
        session.query(DownloadSubmission)
        .filter(
            DownloadSubmission.status.in_(
                [
                    DownloadSubmission.StatusEnum.PENDING,
                    DownloadSubmission.StatusEnum.DOWNLOADING,
                ]
            )
        )
        .count()
    )


def get_download_category(
    tracking_id: int,
    session: Session,
    default_category: Optional[str],
) -> Optional[str]:
    """
    Determine the download category for a submission.

    Priority: tracking-specific category > system default.

    Args:
        tracking_id: Periodical tracking ID
        session: Database session
        default_category: System-wide default category (may be None)

    Returns:
        Category name or None if no category configured
    """
    tracking = session.query(PeriodicalTracking).filter(PeriodicalTracking.id == tracking_id).first()

    if tracking and tracking.download_category:
        logger.debug(
            "[DownloadManager] Using tracked item download_category: %s",
            tracking.download_category,
        )
        return tracking.download_category

    if default_category:
        logger.debug("[DownloadManager] Using default download_category: %s", default_category)
        return default_category

    return None
