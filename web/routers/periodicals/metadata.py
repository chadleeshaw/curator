"""
Metadata operations for periodicals
"""

from datetime import datetime
from typing import Any, Dict

from fastapi import HTTPException

from core.constants.date import NUMBER_TO_MONTH
from core.constants.errors import ErrorMessages
from core.utils import run_in_thread
from models.database import Periodical

from . import _shared

router = _shared.router
logger = _shared.logger


@router.post("/periodicals/{magazine_id}/toggle-special-edition")
async def toggle_special_edition(magazine_id: int, is_special: bool) -> Dict[str, Any]:
    """
    Mark or unmark an issue as a special edition.

    Args:
        magazine_id: ID of the issue to update
        is_special: True to mark as special edition, False to unmark
    """
    try:

        def _db_operation():
            db_session = _shared._session_factory()
            try:
                magazine = db_session.query(Periodical).filter(Periodical.id == magazine_id).first()
                if not magazine:
                    raise HTTPException(status_code=404, detail=ErrorMessages.MAGAZINE_NOT_FOUND)

                # Initialize extra_metadata if needed
                if magazine.extra_metadata is None:
                    magazine.extra_metadata = {}

                # Update special edition status
                if is_special:
                    # Mark as special edition - store the current title as special edition name
                    magazine.extra_metadata["special_edition"] = magazine.title
                    logger.info(f"Marked issue as special edition: {magazine.title}")
                    message = f"Marked '{magazine.title}' as a special edition"
                else:
                    # Unmark as special edition
                    if "special_edition" in magazine.extra_metadata:
                        del magazine.extra_metadata["special_edition"]
                    logger.info(f"Unmarked special edition: {magazine.title}")
                    message = f"Unmarked '{magazine.title}' as special edition"

                # Mark the column as modified for SQLAlchemy to detect the change
                from sqlalchemy.orm.attributes import flag_modified

                flag_modified(magazine, "extra_metadata")

                db_session.commit()

                return {
                    "success": True,
                    "message": message,
                    "is_special_edition": is_special,
                }
            finally:
                db_session.close()

        return await run_in_thread(_db_operation)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Toggle special edition error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/periodicals/{magazine_id}")
async def update_periodical(magazine_id: int, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Update periodical metadata"""
    try:

        def _db_operation():
            db_session = _shared._session_factory()
            try:
                magazine = db_session.query(Periodical).filter(Periodical.id == magazine_id).first()
                if not magazine:
                    raise HTTPException(status_code=404, detail=ErrorMessages.PERIODICAL_NOT_FOUND)

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

                if "special_edition" in updates:
                    if updates["special_edition"]:
                        magazine.extra_metadata["special_edition"] = updates["special_edition"]
                    elif "special_edition" in magazine.extra_metadata:
                        del magazine.extra_metadata["special_edition"]

                # Mark the column as modified for SQLAlchemy to detect the change
                from sqlalchemy.orm.attributes import flag_modified

                flag_modified(magazine, "extra_metadata")

                db_session.commit()
                db_session.refresh(magazine)

                return {
                    "success": True,
                    "message": "Metadata updated successfully",
                    "periodical": {
                        "id": magazine.id,
                        "title": magazine.title,
                        "language": magazine.language,
                        "issue_date": (magazine.issue_date.isoformat() if magazine.issue_date else None),
                        "metadata": magazine.extra_metadata,
                    },
                }
            finally:
                db_session.close()

        return await run_in_thread(_db_operation)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating periodical: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
