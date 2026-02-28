"""
Metadata operations for periodicals
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict

from fastapi import Depends

from core.constants.date import NUMBER_TO_MONTH
from core.utils.db import mark_json_modified, with_db_session
from core.utils.error_handling import handle_api_errors
from core.utils.files import get_library_dir
from services.file_operations import reorganize_periodical_files
from web.utils.responses import success_response

from . import _shared
from web.routers.auth import get_verify_token

router = _shared.router
logger = _shared.logger


@router.post("/periodicals/{magazine_id}/toggle-special-edition")
@handle_api_errors("Toggle special edition", logger)
async def toggle_special_edition(
    magazine_id: int, is_special: bool, _username: str = Depends(get_verify_token)
) -> Dict[str, Any]:
    """
    Mark or unmark an issue as a special edition.

    Args:
        magazine_id: ID of the issue to update
        is_special: True to mark as special edition, False to unmark
    """

    def operation(db):
        periodical = _shared.get_periodical_or_404(db, magazine_id)

        if periodical.derived_metadata is None:
            periodical.derived_metadata = {}

        if is_special:
            periodical.derived_metadata["is_special_edition"] = {
                "value": True,
                "source": "manual",
            }
            periodical.derived_metadata["special_edition_name"] = {
                "value": periodical.title,
                "source": "manual",
            }
            logger.info(f"Marked issue as special edition: {periodical.title}")
            message = f"Marked '{periodical.title}' as a special edition"
        else:
            periodical.derived_metadata["is_special_edition"] = {
                "value": False,
                "source": "manual",
            }
            if "special_edition_name" in periodical.derived_metadata:
                del periodical.derived_metadata["special_edition_name"]
            if "special_edition" in periodical.derived_metadata:
                del periodical.derived_metadata["special_edition"]
            logger.info(f"Unmarked special edition: {periodical.title}")
            message = f"Unmarked '{periodical.title}' as special edition"

        mark_json_modified(periodical, "derived_metadata")

        db.commit()

        return success_response(
            message,
            is_special_edition=is_special,
        )

    return await with_db_session(_shared._session_factory, operation)


@router.put("/periodicals/{magazine_id}")
@handle_api_errors("Update periodical", logger)
async def update_periodical(
    magazine_id: int, updates: Dict[str, Any], _username: str = Depends(get_verify_token)
) -> Dict[str, Any]:
    """Update periodical metadata"""

    def operation(db):
        periodical = _shared.get_periodical_or_404(db, magazine_id)

        has_tracking = periodical.tracking_id is not None

        if "language" in updates and not has_tracking:
            periodical.language = updates["language"]

        if periodical.extra_metadata is None:
            periodical.extra_metadata = {}

        if periodical.derived_metadata is None:
            periodical.derived_metadata = {}

        if "country" in updates and not has_tracking:
            periodical.derived_metadata["country"] = {
                "value": updates["country"],
                "source": "manual",
                "confidence": 1.0,
            }

        year_provided = "year" in updates and updates["year"]
        month_provided = "month" in updates

        if year_provided:
            periodical.derived_metadata["year"] = {
                "value": int(updates["year"]),
                "source": "manual",
                "confidence": 1.0,
            }

        if month_provided:
            periodical.derived_metadata["month_name"] = {
                "value": updates["month"],
                "source": "manual",
                "confidence": 1.0,
            }
            month_num_val, _ = _shared.parse_month_string(updates["month"])
            if month_num_val and month_num_val > 1:
                periodical.derived_metadata["month"] = {
                    "value": month_num_val,
                    "source": "manual",
                    "confidence": 1.0,
                }

        if periodical.issue_date:
            if not year_provided:
                periodical.derived_metadata["year"] = {
                    "value": periodical.issue_date.year,
                    "source": "issue_date",
                    "confidence": 1.0,
                }
            if not month_provided or not updates.get("month"):
                month_name = NUMBER_TO_MONTH.get(periodical.issue_date.month, "")
                if month_name:
                    periodical.derived_metadata["month_name"] = {
                        "value": month_name,
                        "source": "issue_date",
                        "confidence": 1.0,
                    }
                    periodical.derived_metadata["month"] = {
                        "value": periodical.issue_date.month,
                        "source": "issue_date",
                        "confidence": 1.0,
                    }

        if year_provided:
            year = int(updates["year"])
            month_str = updates.get("month", "")
            month_num, _ = _shared.parse_month_string(month_str)

            try:
                periodical.issue_date = datetime(year, month_num, 1, tzinfo=UTC)
            except ValueError:
                logger.warning(f"Invalid date: year={year}, month={month_num}")
                periodical.issue_date = datetime(year, 1, 1, tzinfo=UTC)

        if "issue_number" in updates:
            periodical.derived_metadata["issue_number"] = {
                "value": updates["issue_number"],
                "source": "manual",
                "confidence": 1.0,
            }

        if "volume" in updates:
            periodical.derived_metadata["volume"] = {
                "value": updates["volume"],
                "source": "manual",
                "confidence": 1.0,
            }

        if "cover_page" in updates:
            cover_page_value = updates["cover_page"]
            if cover_page_value and isinstance(cover_page_value, int) and cover_page_value > 0:
                periodical.extra_metadata["cover_page"] = cover_page_value
                logger.info(f"Updated cover page to {cover_page_value} for periodical {magazine_id}")

        if "special_edition" in updates:
            if updates["special_edition"]:
                periodical.derived_metadata["special_edition"] = {
                    "value": updates["special_edition"],
                    "source": "manual",
                }
            elif "special_edition" in periodical.derived_metadata:
                del periodical.derived_metadata["special_edition"]

        mark_json_modified(periodical, "extra_metadata", "derived_metadata")

        db.commit()
        db.refresh(periodical)

        files_reorganized = False
        if year_provided or month_provided:
            library_base_dir = _shared._library_base_dir or get_library_dir(None)
            category_prefix = _shared._category_prefix

            result = reorganize_periodical_files(
                periodical,
                new_title=periodical.title,
                library_base_dir=library_base_dir,
                category_prefix=category_prefix,
                should_update_database=True,
            )
            if result.success and result.files_moved:
                files_reorganized = True
                db.commit()
                db.refresh(periodical)
                logger.info(f"Reorganized files for periodical {magazine_id} after metadata update")
            elif not result.success:
                logger.warning(f"Failed to reorganize files for periodical {magazine_id}: {result.error}")

        return success_response(
            "Metadata updated successfully",
            periodical={
                "id": periodical.id,
                "title": periodical.title,
                "language": periodical.language,
                "issue_date": (periodical.issue_date.isoformat() if periodical.issue_date else None),
                "file_path": periodical.file_path,
                "cover_path": periodical.cover_path,
                "metadata": periodical.extra_metadata,
                "derived_metadata": periodical.derived_metadata,
            },
            files_reorganized=files_reorganized,
        )

    return await with_db_session(_shared._session_factory, operation)
