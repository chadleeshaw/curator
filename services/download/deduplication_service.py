"""
Deduplication service for checking duplicate download submissions.
Prevents multiple downloads of the same content.
"""

import logging
from datetime import timedelta
from typing import Optional, Tuple

from sqlalchemy.orm import Session

from core.parsers import utc_now
from core.utils.fuzzy_matching import get_fuzzy_group_id
from models.database import DownloadSubmission

logger = logging.getLogger(__name__)


class DeduplicationService:
    """Service for detecting and preventing duplicate downloads"""

    @staticmethod
    def check_duplicate_submission(
        result_title: str,
        tracking_id: int,
        session: Session,
        window_hours: int = 24,
    ) -> Tuple[bool, Optional[DownloadSubmission]]:
        """
        Check if a search result has already been submitted for download.

        Uses fuzzy matching to detect duplicates even with slight title variations.
        Checks submissions within a time window to avoid false positives from old downloads.

        Args:
            result_title: Title of the search result
            tracking_id: Periodical tracking ID
            session: Database session
            window_hours: Time window in hours to check for duplicates (default: 24)

        Returns:
            Tuple of (is_duplicate, existing_submission_record)
        """
        fuzzy_group = get_fuzzy_group_id(result_title)

        existing = (
            session.query(DownloadSubmission)
            .filter(
                DownloadSubmission.tracking_id == tracking_id,
                DownloadSubmission.fuzzy_match_group == fuzzy_group,
                DownloadSubmission.status.in_(
                    [
                        DownloadSubmission.StatusEnum.QUEUED,
                        DownloadSubmission.StatusEnum.PENDING,
                        DownloadSubmission.StatusEnum.DOWNLOADING,
                        DownloadSubmission.StatusEnum.COMPLETED,
                    ]
                ),
            )
            .order_by(DownloadSubmission.created_at.desc())
            .first()
        )

        if existing:
            is_completed = existing.status == DownloadSubmission.StatusEnum.COMPLETED
            is_within_window = existing.created_at > utc_now() - timedelta(hours=window_hours)

            if is_completed or is_within_window:
                logger.debug(
                    f"Duplicate found: '{result_title}' matches existing submission "
                    f"(ID: {existing.id}, status: {existing.status.value}, "
                    f"created: {existing.created_at})"
                )
                return True, existing

        return False, None
