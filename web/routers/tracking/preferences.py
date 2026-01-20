"""
Tracking routes - Preferences and updates
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict

from fastapi import HTTPException

from core.constants.errors import ErrorMessages
from core.utils.general import (
    is_special_edition,
    generate_olid,
    cleanup_empty_directories,
)
from models.database import MagazineTracking
from web.schemas import TrackingPreferencesRequest
from core.utils import run_in_thread
from . import _shared
from .merge import _reorganize_magazine_files

# Access global state via _shared module to get current values
router = _shared.router
logger = _shared.logger

import shutil


@router.post("/periodicals/tracking/save")
async def save_tracking_preferences(
    request: TrackingPreferencesRequest,
) -> Dict[str, Any]:
    """Save magazine tracking preferences"""
    try:

        def _save():
            db_session = _shared._session_factory()
            try:
                olid = request.olid or generate_olid(request.title)
                existing = db_session.query(MagazineTracking).filter(MagazineTracking.olid == olid).first()

                if existing:
                    existing.title = request.title
                    existing.category = getattr(request, "category", None)
                    existing.language = getattr(request, "language", "English")
                    existing.country = getattr(request, "country", None)
                    existing.first_publish_year = request.first_publish_year
                    existing.track_all_editions = request.track_all_editions
                    existing.track_new_only = request.track_new_only
                    existing.selected_editions = request.selected_editions
                    existing.selected_years = request.selected_years
                    existing.periodical_metadata = request.metadata
                    existing.last_metadata_update = datetime.now(UTC)
                    tracking = existing
                else:
                    tracking = MagazineTracking(
                        olid=olid,
                        title=request.title,
                        category=getattr(request, "category", None),
                        language=getattr(request, "language", "English"),
                        country=getattr(request, "country", None),
                        first_publish_year=request.first_publish_year,
                        track_all_editions=request.track_all_editions,
                        track_new_only=request.track_new_only,
                        selected_editions=request.selected_editions,
                        selected_years=request.selected_years,
                        periodical_metadata=request.metadata,
                        last_metadata_update=datetime.now(UTC),
                    )
                    db_session.add(tracking)

                db_session.commit()

                return {
                    "tracking_id": tracking.id,
                    "title": tracking.title,
                    "track_all_editions": tracking.track_all_editions,
                    "track_new_only": tracking.track_new_only,
                    "selected_editions": tracking.selected_editions,
                    "selected_count": len([v for v in tracking.selected_editions.values() if v]),
                }
            finally:
                db_session.close()

        result = await run_in_thread(_save)

        # Note: We don't trigger immediate auto-download here to avoid blocking the response.
        # The scheduled auto-download task will pick up changes on its next run.
        # This keeps the API response fast (<100ms instead of 5-6 seconds).

        return {
            "success": True,
            "tracking_id": result["tracking_id"],
            "message": f"Tracking preferences saved for '{request.title}'",
            "track_all_editions": result["track_all_editions"],
            "selected_count": result["selected_count"],
        }
    except Exception as e:
        logger.error(f"Save tracking preferences error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/periodicals/tracking/{tracking_id}")
async def update_tracking(tracking_id: int, updates: dict) -> Dict[str, Any]:
    """Update magazine tracking record"""
    try:

        def _update():
            db_session = _shared._session_factory()
            try:
                tracking = db_session.query(MagazineTracking).filter(MagazineTracking.id == tracking_id).first()
                if not tracking:
                    raise HTTPException(status_code=404, detail=ErrorMessages.TRACKING_NOT_FOUND)

                # Store old title for file reorganization if title is being changed
                old_title = tracking.title
                title_changed = "title" in updates and updates["title"] != old_title

                if "title" in updates:
                    tracking.title = updates["title"]
                if "category" in updates:
                    tracking.category = updates["category"]
                if "language" in updates:
                    tracking.language = updates["language"]
                if "country" in updates:
                    tracking.country = updates["country"]
                if "download_category" in updates:
                    tracking.download_category = updates["download_category"]
                if "track_all_editions" in updates:
                    tracking.track_all_editions = updates["track_all_editions"]
                if "track_new_only" in updates:
                    tracking.track_new_only = updates["track_new_only"]
                if "delete_from_client_on_completion" in updates:
                    tracking.delete_from_client_on_completion = updates["delete_from_client_on_completion"]

                # If title changed, reorganize all files for this tracking record
                files_reorganized = 0
                directories_to_cleanup = set()
                organize_base_dir = None

                if title_changed:
                    from models.database import Magazine

                    # Get organize directory from config
                    organize_base_dir = Path(_shared._storage_config.get("organize_dir", "./local/data")).resolve()
                    category_prefix = _shared._import_config.get("category_prefix", "_")

                    # Get all magazines linked to this tracking record
                    magazines = db_session.query(Magazine).filter(Magazine.tracking_id == tracking_id).all()

                    for magazine in magazines:
                        # Check if this is a special edition
                        is_special = False
                        if magazine.extra_metadata and isinstance(magazine.extra_metadata, dict):
                            is_special = magazine.extra_metadata.get("special_edition") is not None
                        if not is_special:
                            is_special = is_special_edition(magazine.title)

                        # Only reorganize regular editions
                        if not is_special:
                            # Store old title directory for cleanup (parent of year directory)
                            old_pdf_path = Path(magazine.file_path)
                            if old_pdf_path.exists():
                                # Add title directory (grandparent of PDF) not just year directory
                                # Structure: title_dir/year/magazine.pdf
                                title_dir = old_pdf_path.parent.parent
                                directories_to_cleanup.add(title_dir)

                            # Reorganize files to match new title structure
                            new_pdf_path, new_cover_path = _reorganize_magazine_files(
                                magazine,
                                tracking.title,
                                organize_base_dir,
                                category_prefix,
                            )

                            # Update database paths if reorganization succeeded
                            if new_pdf_path:
                                # Check if target path already exists in database (UNIQUE constraint check)
                                existing_record = db_session.query(Magazine).filter_by(file_path=new_pdf_path).first()
                                if existing_record and existing_record.id != magazine.id:
                                    logger.error(
                                        f"Cannot update magazine {magazine.id}: Target path {new_pdf_path} "
                                        f"already exists in database for magazine {existing_record.id}. "
                                        f"This is a data integrity issue that needs manual resolution."
                                    )
                                    # Roll back the file move since we can't update the database
                                    try:
                                        old_pdf_path = Path(magazine.file_path)
                                        if Path(new_pdf_path).exists() and not old_pdf_path.exists():
                                            shutil.move(new_pdf_path, str(old_pdf_path))
                                            logger.info(f"Rolled back file move: {new_pdf_path} -> {old_pdf_path}")
                                    except Exception as rollback_error:
                                        logger.error(
                                            f"Failed to rollback file move for magazine {magazine.id}: {rollback_error}"
                                        )
                                else:
                                    magazine.file_path = new_pdf_path
                                    if new_cover_path:
                                        magazine.cover_path = new_cover_path
                                    files_reorganized += 1
                                    logger.info(
                                        f"Reorganized files for: {magazine.title} ({magazine.issue_date.strftime('%b %Y')})"
                                    )
                            else:
                                logger.warning(
                                    f"Failed to reorganize files for magazine ID {magazine.id}, keeping original paths"
                                )

                            # Update magazine title to match tracking title
                            magazine.title = tracking.title

                db_session.commit()

                # Extract tracking data before closing session
                tracking_data = {
                    "id": tracking.id,
                    "title": tracking.title,
                    "track_all_editions": tracking.track_all_editions,
                    "track_new_only": tracking.track_new_only,
                    "delete_from_client_on_completion": tracking.delete_from_client_on_completion,
                }

                return {
                    "tracking_data": tracking_data,
                    "old_title": old_title,
                    "title_changed": title_changed,
                    "files_reorganized": files_reorganized,
                    "directories_to_cleanup": directories_to_cleanup,
                    "organize_base_dir": organize_base_dir,
                }
            finally:
                db_session.close()

        result = await run_in_thread(_update)
        tracking_data = result["tracking_data"]
        title_changed = result["title_changed"]
        files_reorganized = result["files_reorganized"]
        directories_to_cleanup = result["directories_to_cleanup"]
        organize_base_dir = result["organize_base_dir"]
        old_title = result["old_title"]

        # Clean up empty directories after successful commit
        if title_changed and files_reorganized > 0:
            for directory in directories_to_cleanup:
                if directory.exists():
                    cleanup_empty_directories(directory, organize_base_dir)

            logger.info(
                f"Title changed from '{old_title}' to '{tracking_data['title']}', reorganized {files_reorganized} files"
            )

        # Note: We don't trigger immediate auto-download here to avoid blocking the response.
        # The scheduled auto-download task will pick up changes on its next run.
        # This keeps the API response fast (<100ms instead of 5-6 seconds).

        response = {
            "success": True,
            "message": "Tracking updated successfully",
            "tracking": tracking_data,
        }

        if title_changed:
            response["files_reorganized"] = files_reorganized
            response["message"] = f"Tracking updated successfully. Reorganized {files_reorganized} files."

        return response
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update tracking error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
