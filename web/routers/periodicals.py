"""
Periodicals/Library management routes
"""

import logging
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from models.database import Magazine
from web.schemas import MagazineResponse

router = APIRouter(prefix="/api", tags=["periodicals"])
logger = logging.getLogger(__name__)

# Global state (injected from main app)
_session_factory = None


def set_dependencies(session_factory):
    """Set dependencies from main app"""
    global _session_factory
    _session_factory = session_factory


@router.get("/periodicals")
async def list_periodicals(
    skip: int = 0, limit: int = 50, sort_by: str = "title", sort_order: str = "asc"
) -> Dict[str, Any]:
    """
    List unique periodicals from library (grouped by title).
    Returns one entry per periodical title with the latest issue's metadata.

    Args:
        skip: Number of records to skip for pagination
        limit: Maximum number of records to return
        sort_by: Sort field - "title", "category", or "issue_date" (default: "title")
        sort_order: Sort direction - "asc" or "desc" (default: "asc")

    Returns:
        List of unique periodicals with their metadata
    """
    try:
        db_session = _session_factory()
        try:
            # Validate sort_order
            is_descending = sort_order.lower() == "desc"

            # Group by tracking_id (when present) OR title+language (for untracked items)
            # This allows merged tracking records to show as one entry while preserving
            # separate entries for untracked items
            from sqlalchemy import func, case
            from models.database import MagazineTracking

            # For grouping, use tracking.title when tracking_id exists, otherwise use magazine.title
            # This ensures merged items show under the primary tracking title
            # Subquery to find the max issue_date for each group
            subquery = (
                db_session.query(
                    case(
                        (Magazine.tracking_id.isnot(None), Magazine.tracking_id),
                        else_=Magazine.id
                    ).label("group_key"),
                    Magazine.language,
                    func.max(Magazine.issue_date).label("max_date")
                )
                .group_by("group_key", Magazine.language)
                .subquery()
            )

            # Join to get full magazine record for each group's latest issue
            query = db_session.query(Magazine).join(
                subquery,
                (
                    case(
                        (Magazine.tracking_id.isnot(None), Magazine.tracking_id),
                        else_=Magazine.id
                    ) == subquery.c.group_key
                )
                & (Magazine.language == subquery.c.language)
                & (Magazine.issue_date == subquery.c.max_date)
            )

            # Left join with tracking to get the primary title for display
            query = query.outerjoin(MagazineTracking, Magazine.tracking_id == MagazineTracking.id)

            # Apply sorting - use tracking title when available
            if sort_by == "category":
                # Sort by category from tracking if available, otherwise fall back to magazine category
                sort_expr = (
                    func.coalesce(MagazineTracking.category, Magazine.extra_metadata['category'].astext).desc()
                    if is_descending
                    else func.coalesce(MagazineTracking.category, Magazine.extra_metadata['category'].astext).asc()
                )
                query = query.order_by(sort_expr, func.coalesce(MagazineTracking.title, Magazine.title).asc())
            elif sort_by == "issue_date":
                sort_expr = (
                    Magazine.issue_date.desc()
                    if is_descending
                    else Magazine.issue_date.asc()
                )
                query = query.order_by(sort_expr)
            else:  # Default to title
                sort_expr = (
                    func.coalesce(MagazineTracking.title, Magazine.title).desc()
                    if is_descending
                    else func.coalesce(MagazineTracking.title, Magazine.title).asc()
                )
                query = query.order_by(sort_expr)

            magazines = query.offset(skip).limit(limit).all()

            # Get total count of unique groups
            total_query = db_session.query(
                func.count(func.distinct(  # pylint: disable=not-callable
                    case(
                        (Magazine.tracking_id.isnot(None), Magazine.tracking_id),
                        else_=Magazine.id
                    ).concat('_').concat(func.coalesce(Magazine.language, 'English'))
                ))
            )
            total_titles = total_query.scalar()  # pylint: disable=not-callable

            # Get issue counts for each group
            # For tracked items, count all issues with same tracking_id + language
            # For untracked items, count by title + language
            issue_counts = {}
            for mag in magazines:
                if mag.tracking_id:
                    # Count all magazines with same tracking_id and language
                    key = (mag.tracking_id, mag.language or 'English')
                    if key not in issue_counts:
                        count = db_session.query(Magazine).filter(
                            Magazine.tracking_id == mag.tracking_id,
                            Magazine.language == mag.language
                        ).count()
                        issue_counts[key] = count
                else:
                    # Count by title and language for untracked items
                    key = (mag.title, mag.language or 'English', None)
                    if key not in issue_counts:
                        count = db_session.query(Magazine).filter(
                            Magazine.title == mag.title,
                            Magazine.language == mag.language,
                            Magazine.tracking_id.is_(None)
                        ).count()
                        issue_counts[key] = count

            # Fetch tracking record for each magazine to get display title
            tracking_titles = {}
            for mag in magazines:
                if mag.tracking_id and mag.tracking_id not in tracking_titles:
                    tracking = db_session.query(MagazineTracking).filter(
                        MagazineTracking.id == mag.tracking_id
                    ).first()
                    if tracking:
                        tracking_titles[mag.tracking_id] = tracking.title

            return {
                "periodicals": [
                    {
                        "id": m.id,
                        "title": tracking_titles.get(m.tracking_id, m.title) if m.tracking_id else m.title,
                        "language": m.language or "English",
                        "issue_date": (
                            m.issue_date.isoformat() if m.issue_date else None
                        ),
                        "file_path": m.file_path,
                        "cover_path": m.cover_path,
                        "content_hash": m.content_hash,
                        "tracking_id": m.tracking_id,
                        "created_at": (
                            m.created_at.isoformat() if m.created_at else None
                        ),
                        "updated_at": (
                            m.updated_at.isoformat() if m.updated_at else None
                        ),
                        "metadata": m.extra_metadata,
                        "issue_count": issue_counts.get(
                            (m.tracking_id, m.language or 'English') if m.tracking_id
                            else (m.title, m.language or 'English', None),
                            1
                        ),
                    }
                    for m in magazines
                ],
                "total": total_titles,
                "skip": skip,
                "limit": limit,
            }
        finally:
            db_session.close()

    except Exception as e:
        logger.error(f"List periodicals error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/periodicals/{magazine_id}")
async def get_magazine(magazine_id: int) -> MagazineResponse:
    """Get magazine details"""
    try:
        db_session = _session_factory()
        try:
            magazine = (
                db_session.query(Magazine).filter(Magazine.id == magazine_id).first()
            )

            if not magazine:
                raise HTTPException(status_code=404, detail="Magazine not found")

            return {
                "id": magazine.id,
                "title": magazine.title,
                "language": magazine.language,
                "issue_date": (
                    magazine.issue_date.isoformat() if magazine.issue_date else None
                ),
                "file_path": magazine.file_path,
                "cover_path": magazine.cover_path,
                "content_hash": magazine.content_hash,
                "tracking_id": magazine.tracking_id,
                "created_at": (
                    magazine.created_at.isoformat() if magazine.created_at else None
                ),
                "updated_at": (
                    magazine.updated_at.isoformat() if magazine.updated_at else None
                ),
                "metadata": magazine.extra_metadata,
            }
        finally:
            db_session.close()

    except Exception as e:
        logger.error(f"Get magazine error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/periodicals/{magazine_id}/cover")
async def get_cover(magazine_id: int):
    """Get magazine cover image"""
    try:
        db_session = _session_factory()
        try:
            magazine = (
                db_session.query(Magazine).filter(Magazine.id == magazine_id).first()
            )

            if not magazine or not magazine.cover_path:
                raise HTTPException(status_code=404, detail="Cover not found")

            cover_path = Path(magazine.cover_path)
            if not cover_path.exists():
                raise HTTPException(status_code=404, detail="Cover file not found")

            return FileResponse(cover_path, media_type="image/jpeg")
        finally:
            db_session.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get cover error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/periodicals/{magazine_id}/pdf")
async def get_pdf(magazine_id: int):
    """Get magazine PDF file"""
    try:
        db_session = _session_factory()
        try:
            magazine = (
                db_session.query(Magazine).filter(Magazine.id == magazine_id).first()
            )

            if not magazine:
                raise HTTPException(status_code=404, detail="Magazine not found")

            pdf_path = Path(magazine.file_path)
            if not pdf_path.exists():
                raise HTTPException(status_code=404, detail="PDF file not found")

            return FileResponse(pdf_path, media_type="application/pdf")
        finally:
            db_session.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get PDF error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/periodicals/{magazine_id}/move-to-tracking")
async def move_issue_to_tracking(
    magazine_id: int, target_tracking_id: int
) -> Dict[str, Any]:
    """
    Move a single issue to a different tracking record.
    Useful for correcting misplaced issues.

    Args:
        magazine_id: ID of the issue to move
        target_tracking_id: ID of the tracking record to move the issue to
    """
    try:
        db_session = _session_factory()
        try:
            from models.database import MagazineTracking
            import shutil
            from core.parsers import sanitize_filename
            from core.utils import is_special_edition

            # Get the magazine to move
            magazine = db_session.query(Magazine).filter(Magazine.id == magazine_id).first()
            if not magazine:
                raise HTTPException(status_code=404, detail="Magazine not found")

            # Get the target tracking record
            target_tracking = db_session.query(MagazineTracking).filter(
                MagazineTracking.id == target_tracking_id
            ).first()
            if not target_tracking:
                raise HTTPException(status_code=404, detail="Target tracking record not found")

            old_title = magazine.title
            old_tracking_id = magazine.tracking_id

            # Get organize directory from config or use default
            organize_base_dir = Path("./local/data").resolve()
            category_prefix = "_"

            # Update the magazine's tracking_id
            magazine.tracking_id = target_tracking_id

            # Check if this is a special edition
            is_special = False
            if magazine.extra_metadata and isinstance(magazine.extra_metadata, dict):
                is_special = magazine.extra_metadata.get("special_edition") is not None
            if not is_special:
                is_special = is_special_edition(magazine.title)

            # Only update title and reorganize files for regular editions
            files_reorganized = False
            old_dir_to_cleanup = None
            if not is_special:
                # Store old paths
                old_pdf_path = Path(magazine.file_path)
                old_cover_path = Path(magazine.cover_path) if magazine.cover_path else None

                # Reorganize files to match new title structure
                try:
                    # Extract metadata from current path structure
                    category = magazine.extra_metadata.get("category", "Magazines") if magazine.extra_metadata else "Magazines"
                    language = magazine.language or "English"
                    issue_date = magazine.issue_date

                    # Build new path structure
                    safe_title = sanitize_filename(target_tracking.title)
                    month = issue_date.strftime("%b")
                    year = issue_date.strftime("%Y")
                    filename_base = f"{safe_title} - {month}{year}"

                    category_with_prefix = f"{category_prefix}{category}"
                    target_dir = organize_base_dir / category_with_prefix / safe_title / language / year
                    target_dir.mkdir(parents=True, exist_ok=True)

                    new_pdf_path = target_dir / f"{filename_base}.pdf"
                    new_cover_path = target_dir / f"{filename_base}.jpg" if old_cover_path else None

                    # Handle filename conflicts by appending timestamp
                    if new_pdf_path.exists() and new_pdf_path != old_pdf_path:
                        from datetime import datetime
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filename_base_with_ts = f"{safe_title} - {month}{year} ({timestamp})"
                        new_pdf_path = target_dir / f"{filename_base_with_ts}.pdf"
                        if old_cover_path:
                            new_cover_path = target_dir / f"{filename_base_with_ts}.jpg"

                    # Move PDF file
                    if old_pdf_path.exists() and new_pdf_path != old_pdf_path:
                        # Store directory for cleanup before moving files
                        old_dir_to_cleanup = old_pdf_path.parent
                        shutil.move(str(old_pdf_path), str(new_pdf_path))
                        logger.info(f"Moved PDF: {old_pdf_path} -> {new_pdf_path}")
                        magazine.file_path = str(new_pdf_path)
                        files_reorganized = True
                    elif new_pdf_path == old_pdf_path:
                        # File is already in correct location
                        magazine.file_path = str(new_pdf_path)
                    else:
                        logger.warning(f"PDF file not found: {old_pdf_path}")

                    # Move cover file if it exists
                    if old_cover_path and old_cover_path.exists() and new_cover_path and new_cover_path != old_cover_path:
                        shutil.move(str(old_cover_path), str(new_cover_path))
                        logger.info(f"Moved cover: {old_cover_path} -> {new_cover_path}")
                        magazine.cover_path = str(new_cover_path)
                    elif new_cover_path:
                        magazine.cover_path = str(new_cover_path)

                    # Update title after file operations
                    magazine.title = target_tracking.title

                except Exception as e:
                    logger.error(f"Error reorganizing magazine files: {e}", exc_info=True)
                    # Still update the tracking_id and title even if file move failed
                    magazine.title = target_tracking.title

            db_session.commit()

            # Clean up old directory after successful commit
            if old_dir_to_cleanup and old_dir_to_cleanup.exists():
                _cleanup_empty_directories(old_dir_to_cleanup, organize_base_dir)

            msg = f"Moved issue from '{old_title}' to '{target_tracking.title}'"
            if files_reorganized:
                msg += " and reorganized files"

            logger.info(msg)
            return {
                "success": True,
                "message": msg,
                "old_tracking_id": old_tracking_id,
                "new_tracking_id": target_tracking_id,
                "files_reorganized": files_reorganized
            }
        finally:
            db_session.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Move issue to tracking error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _cleanup_empty_directories(start_path: Path, organize_base_dir: Path):
    """
    Remove empty directories from a path up to the organize base directory.

    Args:
        start_path: Starting directory to check
        organize_base_dir: Base directory (won't delete this)
    """
    try:
        current = start_path
        while current != organize_base_dir and current.exists():
            # Only delete if directory is empty
            if current.is_dir() and not any(current.iterdir()):
                logger.info(f"Removing empty directory: {current}")
                current.rmdir()
                current = current.parent
            else:
                # Stop if we find a non-empty directory
                break
    except Exception as e:
        logger.warning(f"Error cleaning up empty directories: {e}")


@router.post("/periodicals/{magazine_id}/toggle-special-edition")
async def toggle_special_edition(
    magazine_id: int, is_special: bool
) -> Dict[str, Any]:
    """
    Mark or unmark an issue as a special edition.

    Args:
        magazine_id: ID of the issue to update
        is_special: True to mark as special edition, False to unmark
    """
    try:
        db_session = _session_factory()
        try:
            magazine = db_session.query(Magazine).filter(Magazine.id == magazine_id).first()
            if not magazine:
                raise HTTPException(status_code=404, detail="Magazine not found")

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
                "is_special_edition": is_special
            }
        finally:
            db_session.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Toggle special edition error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/periodicals/{magazine_id}")
async def delete_periodical(
    magazine_id: int, delete_files: bool = False, remove_tracking: bool = False, delete_all_issues: bool = False
) -> Dict[str, Any]:
    """
    Delete a periodical from the library

    Args:
        magazine_id: ID of periodical to delete
        delete_files: If True, also delete the PDF and cover files from disk. If False, only remove from database.
        remove_tracking: If True, also remove the tracking record for this periodical.
        delete_all_issues: If True, delete all issues with the same title and language. If False, only delete the single issue.
    """
    try:
        db_session = _session_factory()
        try:
            magazine = (
                db_session.query(Magazine).filter(Magazine.id == magazine_id).first()
            )

            if not magazine:
                raise HTTPException(status_code=404, detail="Magazine not found")

            # Store title and language for potential deletion of all issues
            title = magazine.title
            language = magazine.language

            # Determine which magazines to delete
            if delete_all_issues:
                # Get all magazines with the same title and language
                magazines_to_delete = (
                    db_session.query(Magazine)
                    .filter(Magazine.title == title, Magazine.language == language)
                    .all()
                )
            else:
                # Only delete the single specified magazine
                magazines_to_delete = [magazine]

            # Store file paths for potential deletion
            file_paths_to_delete = []
            for mag in magazines_to_delete:
                pdf_path = Path(mag.file_path)
                cover_path = Path(mag.cover_path) if mag.cover_path else None
                file_paths_to_delete.append((pdf_path, cover_path))

            # Delete database entries
            for mag in magazines_to_delete:
                db_session.delete(mag)
            db_session.commit()

            deleted_count = len(magazines_to_delete)

            # Remove tracking record if requested
            if remove_tracking:
                from models.database import MagazineTracking

                olid = title.lower().replace(" ", "_").replace("-", "_")
                tracking = (
                    db_session.query(MagazineTracking)
                    .filter(MagazineTracking.olid == olid)
                    .first()
                )
                if tracking:
                    db_session.delete(tracking)
                    db_session.commit()
                    logger.info(f"Removed tracking record for: {title}")

            # Delete files from filesystem if requested
            if delete_files:
                files_deleted = 0
                for pdf_path, cover_path in file_paths_to_delete:
                    try:
                        if pdf_path.exists():
                            pdf_path.unlink()
                            files_deleted += 1
                            logger.info(f"Deleted PDF file: {pdf_path}")
                    except Exception as e:
                        logger.warning(f"Could not delete PDF file {pdf_path}: {e}")

                    try:
                        if cover_path and cover_path.exists():
                            cover_path.unlink()
                            logger.info(f"Deleted cover file: {cover_path}")
                    except Exception as e:
                        logger.warning(f"Could not delete cover file {cover_path}: {e}")

                logger.info(f"Deleted {deleted_count} issue(s) and files from disk: {title}")
                if deleted_count > 1:
                    message = f"Deleted {deleted_count} issues of '{title}' and their files from disk"
                else:
                    message = f"Deleted '{title}' and files from disk"
                if remove_tracking:
                    message += " (tracking removed)"
                return {
                    "success": True,
                    "message": message,
                }
            else:
                logger.info(f"Deleted {deleted_count} issue(s) from library (files retained): {title}")
                if deleted_count > 1:
                    message = f"Removed {deleted_count} issues of '{title}' from library (files retained on disk)"
                else:
                    message = f"Removed '{title}' from library (files retained on disk)"
                if remove_tracking:
                    message += " (tracking removed)"
                return {
                    "success": True,
                    "message": message,
                }
        finally:
            db_session.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete periodical error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/purge-database")
async def purge_database() -> Dict[str, Any]:
    """
    Purge all library entries and tracking records from the database.
    Files on disk will NOT be deleted.

    Returns:
        Success message with counts of deleted entries
    """
    try:
        db_session = _session_factory()
        try:
            from models.database import MagazineTracking, DownloadSubmission

            # Count entries before deletion
            magazine_count = db_session.query(Magazine).count()
            tracking_count = db_session.query(MagazineTracking).count()
            download_count = db_session.query(DownloadSubmission).count()

            # Delete all library entries
            db_session.query(Magazine).delete()
            logger.info(f"Purged {magazine_count} magazine entries from database")

            # Delete all tracking records
            db_session.query(MagazineTracking).delete()
            logger.info(f"Purged {tracking_count} tracking records from database")

            # Delete all download submissions
            db_session.query(DownloadSubmission).delete()
            logger.info(f"Purged {download_count} download submissions from database")

            # Commit all deletions
            db_session.commit()

            logger.warning("Database purged successfully. All library and tracking data removed.")

            return {
                "success": True,
                "message": f"Database purged successfully. Removed {magazine_count} library entries, "
                           f"{tracking_count} tracking records, and {download_count} downloads. "
                           f"Files on disk remain untouched.",
                "counts": {
                    "magazines": magazine_count,
                    "tracking": tracking_count,
                    "downloads": download_count,
                }
            }

        finally:
            db_session.close()

    except Exception as e:
        logger.error(f"Purge database error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
