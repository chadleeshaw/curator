"""
Metadata operations for periodicals
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict


from core.constants.date import NUMBER_TO_MONTH
from core.utils.db import mark_json_modified, with_db_session
from core.utils.error_handling import handle_api_errors
from core.utils.files import get_library_dir
from services.file_operations import reorganize_periodical_files
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
            # Mark as special edition - store as structured data with proper field names
            magazine.derived_metadata["is_special_edition"] = {
                "value": True,
                "source": "manual",
            }
            magazine.derived_metadata["special_edition_name"] = {
                "value": magazine.title,
                "source": "manual",
            }
            logger.info(f"Marked issue as special edition: {magazine.title}")
            message = f"Marked '{magazine.title}' as a special edition"
        else:
            # Unmark as special edition - set to false (not delete!) so it overrides
            # any parsed_metadata fallback (e.g., OCR detected "anniversary issue")
            magazine.derived_metadata["is_special_edition"] = {
                "value": False,
                "source": "manual",
            }
            if "special_edition_name" in magazine.derived_metadata:
                del magazine.derived_metadata["special_edition_name"]
            # Also remove legacy field if present
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

        # Ensure derived_metadata is initialized
        if magazine.derived_metadata is None:
            magazine.derived_metadata = {}

        # Country can only be updated if NOT linked to tracking
        if "country" in updates and not has_tracking:
            magazine.derived_metadata["country"] = {
                "value": updates["country"],
                "source": "manual",
                "confidence": 1.0,
            }

        # Handle year and month updates
        year_provided = "year" in updates and updates["year"]
        month_provided = "month" in updates

        # Update derived_metadata fields (structured with source/confidence)
        if year_provided:
            magazine.derived_metadata["year"] = {
                "value": int(updates["year"]),
                "source": "manual",
                "confidence": 1.0,
            }

        if month_provided:
            magazine.derived_metadata["month_name"] = {
                "value": updates["month"],
                "source": "manual",
                "confidence": 1.0,
            }
            # Also store numeric month if parseable
            month_num_val, _ = _shared.parse_month_string(updates["month"])
            if month_num_val and month_num_val > 1:  # parse_month_string defaults to 1
                magazine.derived_metadata["month"] = {
                    "value": month_num_val,
                    "source": "manual",
                    "confidence": 1.0,
                }

        # Auto-populate from issue_date if fields not provided
        if magazine.issue_date:
            if not year_provided:
                magazine.derived_metadata["year"] = {
                    "value": magazine.issue_date.year,
                    "source": "issue_date",
                    "confidence": 1.0,
                }
            if not month_provided or not updates.get("month"):
                month_name = NUMBER_TO_MONTH.get(magazine.issue_date.month, "")
                if month_name:
                    magazine.derived_metadata["month_name"] = {
                        "value": month_name,
                        "source": "issue_date",
                        "confidence": 1.0,
                    }
                    magazine.derived_metadata["month"] = {
                        "value": magazine.issue_date.month,
                        "source": "issue_date",
                        "confidence": 1.0,
                    }

        # Reconstruct issue_date when year is provided
        # This keeps the database field in sync for sorting/filtering
        if year_provided:
            year = int(updates["year"])
            month_str = updates.get("month", "")
            month_num, _ = _shared.parse_month_string(month_str)

            try:
                magazine.issue_date = datetime(year, month_num, 1, tzinfo=UTC)
            except ValueError:
                # Invalid date (e.g., Feb 30) - default to year start
                logger.warning(f"Invalid date: year={year}, month={month_num}")
                magazine.issue_date = datetime(year, 1, 1, tzinfo=UTC)

        if "issue_number" in updates:
            magazine.derived_metadata["issue_number"] = {
                "value": updates["issue_number"],
                "source": "manual",
                "confidence": 1.0,
            }

        if "volume" in updates:
            magazine.derived_metadata["volume"] = {
                "value": updates["volume"],
                "source": "manual",
                "confidence": 1.0,
            }

        # Handle cover page number (stored in extra_metadata)
        if "cover_page" in updates:
            cover_page_value = updates["cover_page"]
            if cover_page_value and isinstance(cover_page_value, int) and cover_page_value > 0:
                magazine.extra_metadata["cover_page"] = cover_page_value
                logger.info(f"Updated cover page to {cover_page_value} for magazine {magazine_id}")

        # Handle special edition in derived_metadata (structured storage)
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

        # Reorganize files if date-affecting metadata changed (year/month)
        # This keeps the filesystem paths in sync with metadata
        files_reorganized = False
        if year_provided or month_provided:
            library_base_dir = _shared._library_base_dir or get_library_dir(None)
            category_prefix = _shared._category_prefix

            result = reorganize_periodical_files(
                magazine,
                new_title=magazine.title,
                library_base_dir=library_base_dir,
                category_prefix=category_prefix,
                update_db=True,
            )
            if result.success and result.files_moved:
                files_reorganized = True
                db.commit()
                db.refresh(magazine)
                logger.info(f"Reorganized files for periodical {magazine_id} after metadata update")
            elif not result.success:
                logger.warning(f"Failed to reorganize files for periodical {magazine_id}: {result.error}")

        return success_response(
            "Metadata updated successfully",
            periodical={
                "id": magazine.id,
                "title": magazine.title,
                "language": magazine.language,
                "issue_date": (magazine.issue_date.isoformat() if magazine.issue_date else None),
                "file_path": magazine.file_path,
                "cover_path": magazine.cover_path,
                "metadata": magazine.extra_metadata,
                "derived_metadata": magazine.derived_metadata,
            },
            files_reorganized=files_reorganized,
        )

    return await with_db_session(_shared._session_factory, operation)
