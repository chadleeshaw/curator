"""
Tracking routes - Merge operations
"""

import shutil
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException

from core.constants.errors import ErrorMessages
from core.utils import run_in_thread
from core.utils.db import with_db_session
from core.utils.error_handling import handle_api_errors
from core.utils.files import get_library_dir, get_category_prefix
from core.utils.general import cleanup_empty_directories, is_special_edition
from models.database import PeriodicalTracking
from services.file_operations import reorganize_periodical_files
from web.schemas import APIError

from . import _shared

# Access global state via _shared module to get current values
router = _shared.router
logger = _shared.logger


def _reorganize_periodical_files(
    periodical, new_title: str, library_base_dir: Path, category_prefix: str = "_"
) -> Tuple[Optional[str], Optional[str]]:
    """
    Reorganize periodical files to match new title structure.

    This is a wrapper around the shared reorganize_periodical_files utility.

    Args:
        periodical: Periodical database object
        new_title: New title to use for folder organization
        library_base_dir: Base directory for organized files
        category_prefix: Prefix for category folders (default: "_")

    Returns:
        Tuple of (new_pdf_path, new_cover_path) or (None, None) if failed
    """
    result = reorganize_periodical_files(
        periodical,
        new_title=new_title,
        library_base_dir=library_base_dir,
        category_prefix=category_prefix,
        update_db=True,
    )
    if result.success:
        return result.new_pdf_path, result.new_cover_path
    else:
        return None, None


@router.post(
    "/periodicals/tracking/{target_id}/merge",
    summary="Merge tracking records",
    description="Merge multiple tracking records into one. Magazines and download submissions from source records will be reassigned to the target record. Files will be reorganized to match the target title structure.",
    responses={
        200: {
            "description": "Tracking records merged successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Merged 2 tracking records into 'Wired Magazine'",
                        "periodicals_moved": 5,
                        "submissions_moved": 10,
                        "files_reorganized": 5,
                    }
                }
            },
        },
        400: {"description": "Invalid input", "model": APIError},
        404: {"description": ErrorMessages.TRACKING_NOT_FOUND, "model": APIError},
        500: {"description": "Failed to merge tracking", "model": APIError},
    },
)
@handle_api_errors("Merge tracking records", logger)
async def merge_tracking(target_id: int, source_ids: Dict[str, list[int]]) -> Dict[str, Any]:
    """
    Merge multiple tracking records into a single target record.

    Args:
        target_id: The tracking record to merge into (will be kept)
        source_ids: Dict with 'source_ids' key containing list of tracking IDs to merge from (will be deleted)

    Returns:
        Dict with merge results including counts of magazines and submissions moved
    """
    if not source_ids.get("source_ids"):
        raise HTTPException(status_code=400, detail="No source tracking IDs provided")

    source_id_list = source_ids["source_ids"]

    if target_id in source_id_list:
        raise HTTPException(status_code=400, detail="Target tracking ID cannot be in source list")

    def operation(db):
        from models.database import Periodical, DownloadSubmission

        # Get target tracking record
        target = db.query(PeriodicalTracking).filter(PeriodicalTracking.id == target_id).first()
        if not target:
            raise HTTPException(status_code=404, detail="Target tracking record not found")

        # Get source tracking records
        sources = db.query(PeriodicalTracking).filter(PeriodicalTracking.id.in_(source_id_list)).all()
        if len(sources) != len(source_id_list):
            raise HTTPException(
                status_code=404,
                detail="One or more source tracking records not found",
            )

        periodicals_moved = 0
        submissions_moved = 0
        files_reorganized = 0
        directories_to_cleanup = set()

        # Get library directory and category prefix from config
        library_base_dir = get_library_dir(_shared._storage_config)
        category_prefix = get_category_prefix(_shared._import_config)

        # Move periodicals from source to target
        for source in sources:
            # Update periodicals to point to target tracking and normalize title
            periodicals = db.query(Periodical).filter(Periodical.tracking_id == source.id).all()
            for periodical in periodicals:
                periodical.tracking_id = target.id

                # Only update title if this is NOT a special edition
                # Special editions need to keep their distinct title to be grouped separately
                is_special = False
                if periodical.extra_metadata and isinstance(periodical.extra_metadata, dict):
                    is_special = periodical.extra_metadata.get("special_edition") is not None

                # Also check title using the is_special_edition function
                if not is_special:
                    is_special = is_special_edition(periodical.title)

                # Only normalize title and reorganize files for regular editions
                if not is_special:
                    # Store old title directory for cleanup (parent of year directory)
                    old_pdf_path = Path(periodical.file_path)
                    if old_pdf_path.exists():
                        # Add title directory (grandparent of PDF) not just year directory
                        # Structure: title_dir/year/magazine.pdf
                        title_dir = old_pdf_path.parent.parent
                        directories_to_cleanup.add(title_dir)

                    # Reorganize files to match new title structure
                    new_pdf_path, new_cover_path = _reorganize_periodical_files(
                        periodical,
                        target.title,
                        library_base_dir,
                        category_prefix,
                    )

                    # Update database paths if reorganization succeeded
                    if new_pdf_path:
                        # Check if target path already exists in database (UNIQUE constraint check)
                        existing_record = db.query(Periodical).filter_by(file_path=new_pdf_path).first()
                        if existing_record and existing_record.id != periodical.id:
                            logger.error(
                                f"Cannot update periodical {periodical.id}: Target path {new_pdf_path} "
                                f"already exists in database for periodical {existing_record.id}. "
                                f"This is a data integrity issue that needs manual resolution."
                            )
                            # Roll back the file move since we can't update the database
                            try:
                                old_pdf_path = Path(periodical.file_path)
                                if Path(new_pdf_path).exists() and not old_pdf_path.exists():
                                    shutil.move(new_pdf_path, str(old_pdf_path))
                                    logger.info(f"Rolled back file move: {new_pdf_path} -> {old_pdf_path}")
                            except Exception as rollback_error:
                                logger.error(
                                    f"Failed to rollback file move for periodical {periodical.id}: {rollback_error}"
                                )
                        else:
                            periodical.file_path = new_pdf_path
                            if new_cover_path:
                                periodical.cover_path = new_cover_path
                            files_reorganized += 1
                            logger.info(
                                f"Reorganized files for: {periodical.title} ({periodical.issue_date.strftime('%b %Y')})"
                            )
                    else:
                        logger.warning(
                            f"Failed to reorganize files for periodical ID {periodical.id}, keeping original paths"
                        )

                    # Update title after file operations
                    periodical.title = target.title

                periodicals_moved += 1

            # Update download submissions to point to target tracking
            submissions = db.query(DownloadSubmission).filter(DownloadSubmission.tracking_id == source.id).all()
            for submission in submissions:
                submission.tracking_id = target.id
                submissions_moved += 1

            # Delete source tracking record
            db.delete(source)

        db.commit()

        # Clean up empty directories after successful commit
        for directory in directories_to_cleanup:
            if directory.exists():
                cleanup_empty_directories(directory, library_base_dir)

        source_titles = [s.title for s in sources]
        logger.info(
            f"Merged {len(sources)} tracking records ({', '.join(source_titles)}) into '{target.title}' (ID: {target_id}). "
            f"Moved {periodicals_moved} magazines, reorganized {files_reorganized} files."
        )

        return {
            "success": True,
            "message": f"Merged {len(sources)} tracking record{'s' if len(sources) > 1 else ''} into '{target.title}'",
            "periodicals_moved": periodicals_moved,
            "submissions_moved": submissions_moved,
            "files_reorganized": files_reorganized,
            "merged_titles": source_titles,
        }

    return await with_db_session(_shared._session_factory, operation)
