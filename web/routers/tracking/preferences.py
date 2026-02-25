"""
Tracking routes - Preferences and updates
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict

from fastapi import HTTPException

from core.constants.category import DEFAULT_CATEGORY
from core.constants.errors import ErrorMessages
from core.constants.language import DEFAULT_LANGUAGE
from core.utils.db import check_file_path_conflict, with_db_session
from core.utils.error_handling import handle_api_errors
from core.utils.files import get_library_dir, get_category_prefix
from core.utils.general import (
    is_special_edition,
    generate_olid,
    cleanup_empty_directories,
)
from core.utils.metadata_builder import is_periodical_special_edition, get_derived_field
from models.database import PeriodicalTracking
from web.schemas import TrackingPreferencesRequest
from web.utils.responses import success_response
from . import _shared
from .merge import _reorganize_periodical_files

# Access global state via _shared module to get current values
router = _shared.router
logger = _shared.logger

import shutil


@router.post("/periodicals/tracking/save")
@handle_api_errors("Save tracking preferences", logger)
async def save_tracking_preferences(
    request: TrackingPreferencesRequest,
) -> Dict[str, Any]:
    """Save magazine tracking preferences"""

    def operation(db):
        olid = request.olid or generate_olid(request.title)
        existing = (
            db.query(PeriodicalTracking).filter(PeriodicalTracking.olid == olid).first()
        )

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
            tracking = PeriodicalTracking(
                user_id=1,
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
            db.add(tracking)

        db.commit()

        return {
            "tracking_id": tracking.id,
            "title": tracking.title,
            "track_all_editions": tracking.track_all_editions,
            "track_new_only": tracking.track_new_only,
            "selected_editions": tracking.selected_editions,
            "selected_count": len(
                [v for v in tracking.selected_editions.values() if v]
            ),
        }

    result = await with_db_session(_shared._session_factory, operation)

    # Note: We don't trigger immediate auto-download here to avoid blocking the response.
    # The scheduled auto-download task will pick up changes on its next run.
    # This keeps the API response fast (<100ms instead of 5-6 seconds).

    return success_response(
        f"Tracking preferences saved for '{request.title}'",
        tracking_id=result["tracking_id"],
        track_all_editions=result["track_all_editions"],
        selected_count=result["selected_count"],
    )


@router.post("/periodicals/tracking/{tracking_id}/reorganize")
@handle_api_errors("Reorganize tracking files", logger)
async def reorganize_tracking_files(tracking_id: int) -> Dict[str, Any]:
    """
    Reorganize all files for a specific tracking record to match its organization pattern.

    This is called after a user changes the organization pattern for a periodical
    and confirms they want to reorganize existing files.
    """

    def operation(db):
        tracking = (
            db.query(PeriodicalTracking)
            .filter(PeriodicalTracking.id == tracking_id)
            .first()
        )
        if not tracking:
            raise HTTPException(
                status_code=404, detail=ErrorMessages.TRACKING_NOT_FOUND
            )

        from models.database import Periodical

        # Get library directory and category prefix from config
        library_base_dir = get_library_dir(_shared._storage_config)
        category_prefix = get_category_prefix(_shared._import_config)

        # Get organization pattern (per-periodical or global default)
        organization_pattern = tracking.organization_pattern

        # Get all periodicals linked to this tracking record
        periodicals = (
            db.query(Periodical).filter(Periodical.tracking_id == tracking_id).all()
        )

        files_reorganized = 0
        files_failed = 0
        directories_to_cleanup = set()

        # Use FileOrganizer to reorganize files with the pattern
        from services.file_organizer import FileOrganizer

        organizer = FileOrganizer(
            str(library_base_dir), category_prefix=category_prefix
        )

        for periodical in periodicals:
            # Check if this is a special edition
            is_special = is_periodical_special_edition(periodical)

            # Only reorganize regular editions
            if not is_special:
                # Store old directory for cleanup
                old_pdf_path = Path(periodical.file_path)
                if old_pdf_path.exists():
                    title_dir = old_pdf_path.parent.parent
                    directories_to_cleanup.add(title_dir)

                try:
                    # Build metadata dict for organizer
                    metadata = {
                        "title": tracking.title,
                        "issue_date": periodical.issue_date,
                        "year": periodical.issue_date.year,
                        "month_name": periodical.issue_date.strftime("%B"),
                        "language": get_derived_field(periodical, "language")
                        or DEFAULT_LANGUAGE,
                        "volume": get_derived_field(periodical, "volume"),
                        "issue_number": get_derived_field(periodical, "issue_number"),
                    }

                    # Get category from metadata
                    category = (
                        periodical.extra_metadata.get("category")
                        if periodical.extra_metadata
                        else DEFAULT_CATEGORY
                    )

                    # Reorganize using FileOrganizer with custom pattern
                    new_pdf_path = organizer.organize(
                        old_pdf_path, metadata, category, organization_pattern
                    )

                    if new_pdf_path:
                        # Check for UNIQUE constraint conflicts
                        if check_file_path_conflict(
                            db, str(new_pdf_path), periodical.id
                        ):
                            logger.error(
                                f"Cannot update periodical {periodical.id}: Target path {new_pdf_path} "
                                f"already exists in database for different periodical."
                            )
                            files_failed += 1
                            # Roll back the file move
                            try:
                                if new_pdf_path.exists() and not old_pdf_path.exists():
                                    shutil.move(str(new_pdf_path), str(old_pdf_path))
                            except Exception as rollback_error:
                                logger.error(
                                    f"Failed to rollback file move: {rollback_error}"
                                )
                        else:
                            periodical.file_path = str(new_pdf_path)
                            # Cover path is handled by organizer
                            files_reorganized += 1
                            logger.info(
                                f"Reorganized: {periodical.title} ({periodical.issue_date.strftime('%b %Y')})"
                            )
                    else:
                        logger.warning(
                            f"Failed to reorganize periodical ID {periodical.id}"
                        )
                        files_failed += 1
                except Exception as e:
                    logger.error(
                        f"Error reorganizing periodical ID {periodical.id}: {e}",
                        exc_info=True,
                    )
                    files_failed += 1

        db.commit()

        return {
            "files_reorganized": files_reorganized,
            "files_failed": files_failed,
            "directories_to_cleanup": directories_to_cleanup,
            "library_base_dir": library_base_dir,
        }

    result = await with_db_session(_shared._session_factory, operation)
    files_reorganized = result["files_reorganized"]
    files_failed = result["files_failed"]
    directories_to_cleanup = result["directories_to_cleanup"]
    library_base_dir = result["library_base_dir"]

    # Clean up empty directories
    for directory in directories_to_cleanup:
        if directory.exists():
            cleanup_empty_directories(directory, library_base_dir)

    message = f"Successfully reorganized {files_reorganized} file(s)"
    if files_failed > 0:
        message += f" ({files_failed} failed)"

    return success_response(
        message,
        files_reorganized=files_reorganized,
        files_failed=files_failed,
    )


@router.put("/periodicals/tracking/{tracking_id}")
@handle_api_errors("Update tracking", logger)
async def update_tracking(tracking_id: int, updates: dict) -> Dict[str, Any]:
    """Update magazine tracking record"""

    def operation(db):
        tracking = (
            db.query(PeriodicalTracking)
            .filter(PeriodicalTracking.id == tracking_id)
            .first()
        )
        if not tracking:
            raise HTTPException(
                status_code=404, detail=ErrorMessages.TRACKING_NOT_FOUND
            )

        # Store old values for change detection
        old_title = tracking.title
        old_language = tracking.language
        old_pattern = tracking.organization_pattern
        old_aliases = tracking.search_aliases
        title_changed = "title" in updates and updates["title"] != old_title
        language_changed = "language" in updates and updates["language"] != old_language
        pattern_changed = (
            "organization_pattern" in updates
            and updates["organization_pattern"] != old_pattern
        )
        aliases_changed = (
            "search_aliases" in updates and updates["search_aliases"] != old_aliases
        )

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
            tracking.delete_from_client_on_completion = updates[
                "delete_from_client_on_completion"
            ]
        if "organization_pattern" in updates:
            tracking.organization_pattern = updates["organization_pattern"]
        if "search_aliases" in updates:
            tracking.search_aliases = updates["search_aliases"]

        # If title changed, reorganize all files for this tracking record
        files_reorganized = 0
        directories_to_cleanup = set()
        library_base_dir = None

        if title_changed:
            from models.database import Periodical

            # Get library directory and category prefix from config
            library_base_dir = get_library_dir(_shared._storage_config)
            category_prefix = get_category_prefix(_shared._import_config)

            # Get all periodicals linked to this tracking record
            periodicals = (
                db.query(Periodical).filter(Periodical.tracking_id == tracking_id).all()
            )

            for periodical in periodicals:
                # Check if this is a special edition
                is_special = is_periodical_special_edition(periodical)

                # Only reorganize regular editions
                if not is_special:
                    # Store old title directory for cleanup (parent of year directory)
                    old_pdf_path = Path(periodical.file_path)
                    if old_pdf_path.exists():
                        # Add title directory (grandparent of PDF) not just year directory
                        # Structure: title_dir/year/periodical.pdf
                        title_dir = old_pdf_path.parent.parent
                        directories_to_cleanup.add(title_dir)

                    # Reorganize files to match new title structure
                    new_pdf_path, new_cover_path = _reorganize_periodical_files(
                        periodical, tracking.title, library_base_dir, category_prefix
                    )

                    # Update database paths if reorganization succeeded
                    if new_pdf_path:
                        # Check if target path already exists in database (UNIQUE constraint check)
                        if check_file_path_conflict(db, new_pdf_path, periodical.id):
                            logger.error(
                                f"Cannot update periodical {periodical.id}: Target path {new_pdf_path} "
                                f"already exists in database for different periodical. "
                                f"This is a data integrity issue that needs manual resolution."
                            )
                            # Roll back the file move since we can't update the database
                            try:
                                old_pdf_path = Path(periodical.file_path)
                                if (
                                    Path(new_pdf_path).exists()
                                    and not old_pdf_path.exists()
                                ):
                                    shutil.move(new_pdf_path, str(old_pdf_path))
                                    logger.info(
                                        f"Rolled back file move: {new_pdf_path} -> {old_pdf_path}"
                                    )
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

                    # Update periodical title to match tracking title
                    periodical.title = tracking.title

        # If language changed, update all linked periodicals to match new language
        language_updates = 0
        if language_changed:
            from models.database import Periodical

            # Get all periodicals linked to this tracking record
            periodicals = (
                db.query(Periodical).filter(Periodical.tracking_id == tracking_id).all()
            )

            for periodical in periodicals:
                # Update language to match tracking
                if periodical.language != tracking.language:
                    periodical.language = tracking.language
                    language_updates += 1
                    logger.info(
                        f"Updated language for: {periodical.title} ({periodical.issue_date.strftime('%b %Y')}) "
                        f"from '{old_language}' to '{tracking.language}'"
                    )

        db.commit()

        # Count files affected by pattern change (for confirmation prompt)
        files_affected_by_pattern = 0
        if pattern_changed:
            from models.database import Periodical

            files_affected_by_pattern = (
                db.query(Periodical)
                .filter(Periodical.tracking_id == tracking_id)
                .count()
            )

        # Extract tracking data before closing session
        tracking_data = {
            "id": tracking.id,
            "title": tracking.title,
            "language": tracking.language,
            "track_all_editions": tracking.track_all_editions,
            "track_new_only": tracking.track_new_only,
            "delete_from_client_on_completion": tracking.delete_from_client_on_completion,
            "search_aliases": tracking.search_aliases,
            "organization_pattern": tracking.organization_pattern,
        }

        return {
            "tracking_data": tracking_data,
            "old_title": old_title,
            "old_language": old_language,
            "title_changed": title_changed,
            "language_changed": language_changed,
            "aliases_changed": aliases_changed,
            "language_updates": language_updates,
            "pattern_changed": pattern_changed,
            "files_affected_by_pattern": files_affected_by_pattern,
            "files_reorganized": files_reorganized,
            "directories_to_cleanup": directories_to_cleanup,
            "library_base_dir": library_base_dir,
        }

    result = await with_db_session(_shared._session_factory, operation)
    tracking_data = result["tracking_data"]
    title_changed = result["title_changed"]
    language_changed = result["language_changed"]
    aliases_changed = result["aliases_changed"]
    language_updates = result["language_updates"]
    pattern_changed = result["pattern_changed"]
    files_affected_by_pattern = result["files_affected_by_pattern"]
    files_reorganized = result["files_reorganized"]
    directories_to_cleanup = result["directories_to_cleanup"]
    library_base_dir = result["library_base_dir"]
    old_title = result["old_title"]
    old_language = result["old_language"]

    # Clean up empty directories after successful commit
    if title_changed and files_reorganized > 0:
        for directory in directories_to_cleanup:
            if directory.exists():
                cleanup_empty_directories(directory, library_base_dir)

        logger.info(
            f"Title changed from '{old_title}' to '{tracking_data['title']}', reorganized {files_reorganized} files"
        )

    # Log language changes
    if language_changed and language_updates > 0:
        logger.info(
            f"Language changed from '{old_language}' to '{tracking_data.get('language', 'English')}', "
            f"updated {language_updates} periodical records"
        )

    # Reset skipped feed entries when title or aliases change so they get
    # re-evaluated against the updated search terms on the next auto-download cycle
    if (title_changed or aliases_changed) and _shared._feed_sync_service:
        try:
            reset_count = _shared._feed_sync_service.reset_skipped_entries()
            if reset_count > 0:
                logger.info(
                    f"Reset {reset_count} feed entries for re-evaluation after tracking update"
                )
        except Exception:
            logger.warning("Failed to reset skipped feed entries after tracking update")

    # Note: We don't trigger immediate auto-download here to avoid blocking the response.
    # The scheduled auto-download task will pick up changes on its next run.
    # This keeps the API response fast (<100ms instead of 5-6 seconds).

    response = success_response(
        "Tracking updated successfully",
        tracking=tracking_data,
    )

    # Build informative message about changes
    messages = []
    if title_changed:
        response["files_reorganized"] = files_reorganized
        messages.append(f"Reorganized {files_reorganized} files")
    if language_changed:
        response["language_updates"] = language_updates
        messages.append(f"Updated language for {language_updates} periodical records")

    if messages:
        response["message"] = f"Tracking updated successfully. {'. '.join(messages)}."

    # If pattern changed, include count for confirmation prompt
    if pattern_changed:
        response["pattern_changed"] = True
        response["files_affected"] = files_affected_by_pattern

    return response
