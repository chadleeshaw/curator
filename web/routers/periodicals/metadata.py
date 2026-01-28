"""
Metadata operations for periodicals
"""

from datetime import datetime
from typing import Any, Dict


from core.constants.date import NUMBER_TO_MONTH
from core.utils.db import mark_json_modified, with_db_session
from core.utils.error_handling import handle_api_errors
from web.utils.responses import success_response

from . import _shared

router = _shared.router
logger = _shared.logger


@router.post("/periodicals/{magazine_id}/toggle-special-edition")
@handle_api_errors("Toggle special edition", logger)
async def toggle_special_edition(magazine_id: int, is_special: bool) -> Dict[str, Any]:
    """
    Mark or unmark an issue as a special edition.

    Args:
        magazine_id: ID of the issue to update
        is_special: True to mark as special edition, False to unmark
    """

    def operation(db):
        magazine = _shared.get_periodical_or_404(db, magazine_id)

        # Initialize derived_metadata if needed
        if magazine.derived_metadata is None:
            magazine.derived_metadata = {}

        # Update special edition status in derived_metadata
        if is_special:
            # Mark as special edition - store as structured data
            magazine.derived_metadata["special_edition"] = {
                "value": magazine.title,
                "source": "manual",
            }
            logger.info(f"Marked issue as special edition: {magazine.title}")
            message = f"Marked '{magazine.title}' as a special edition"
        else:
            # Unmark as special edition
            if "special_edition" in magazine.derived_metadata:
                del magazine.derived_metadata["special_edition"]
            logger.info(f"Unmarked special edition: {magazine.title}")
            message = f"Unmarked '{magazine.title}' as special edition"

        # Mark the column as modified for SQLAlchemy to detect the change
        mark_json_modified(magazine, "derived_metadata")

        db.commit()

        return success_response(
            message,
            is_special_edition=is_special,
        )

    return await with_db_session(_shared._session_factory, operation)


@router.put("/periodicals/{magazine_id}")
@handle_api_errors("Update periodical", logger)
async def update_periodical(magazine_id: int, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Update periodical metadata"""

    def operation(db):
        magazine = _shared.get_periodical_or_404(db, magazine_id)

        # Check if this magazine is linked to tracking
        has_tracking = magazine.tracking_id is not None

        # Update allowed fields
        # Language can only be updated if NOT linked to tracking
        if "language" in updates and not has_tracking:
            magazine.language = updates["language"]

        # Update extra_metadata fields
        if magazine.extra_metadata is None:
            magazine.extra_metadata = {}

        # Country can only be updated if NOT linked to tracking
        if "country" in updates and not has_tracking:
            magazine.extra_metadata["country"] = updates["country"]

        # Handle year and month updates
        year_provided = "year" in updates and updates["year"]
        month_provided = "month" in updates

        # Update metadata fields
        if year_provided:
            magazine.extra_metadata["year"] = updates["year"]

        if month_provided:
            magazine.extra_metadata["month"] = updates["month"]

        # Auto-populate from issue_date if fields not provided
        if magazine.issue_date:
            if not year_provided:
                magazine.extra_metadata["year"] = magazine.issue_date.year
            if not month_provided or not updates.get("month"):
                magazine.extra_metadata["month"] = NUMBER_TO_MONTH.get(magazine.issue_date.month, "")

        # Reconstruct issue_date when year is provided
        # This keeps the database field in sync for sorting/filtering
        if year_provided:
            year = int(updates["year"])
            month_str = updates.get("month", "")
            month_num, _ = _shared.parse_month_string(month_str)

            try:
                magazine.issue_date = datetime(year, month_num, 1)
            except ValueError:
                # Invalid date (e.g., Feb 30) - default to year start
                logger.warning(f"Invalid date: year={year}, month={month_num}")
                magazine.issue_date = datetime(year, 1, 1)

        if "issue_number" in updates:
            magazine.extra_metadata["issue_number"] = updates["issue_number"]

        if "volume" in updates:
            magazine.extra_metadata["volume"] = updates["volume"]

        # Handle special edition in derived_metadata (structured storage)
        if magazine.derived_metadata is None:
            magazine.derived_metadata = {}

        if "special_edition" in updates:
            if updates["special_edition"]:
                # Store as structured data with source indicator
                magazine.derived_metadata["special_edition"] = {
                    "value": updates["special_edition"],
                    "source": "manual",
                }
            elif "special_edition" in magazine.derived_metadata:
                del magazine.derived_metadata["special_edition"]

        # Mark both columns as modified for SQLAlchemy to detect changes
        mark_json_modified(magazine, "extra_metadata", "derived_metadata")

        db.commit()
        db.refresh(magazine)

        return success_response(
            "Metadata updated successfully",
            periodical={
                "id": magazine.id,
                "title": magazine.title,
                "language": magazine.language,
                "issue_date": (magazine.issue_date.isoformat() if magazine.issue_date else None),
                "metadata": magazine.extra_metadata,
            },
        )

    return await with_db_session(_shared._session_factory, operation)
