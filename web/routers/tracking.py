"""
Periodical tracking routes
"""

import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, HTTPException, Query

from core.parsers import sanitize_filename
from core.utils import is_special_edition
from models.database import MagazineTracking
from models.database import SearchResult as DBSearchResult
from web.schemas import APIError, TrackingPreferencesRequest

router = APIRouter(prefix="/api", tags=["tracking"])
logger = logging.getLogger(__name__)

# Global state (injected from main app)
_session_factory = None
_search_providers = None
_auto_download_task_func = None


def set_dependencies(session_factory, search_providers, auto_download_task=None):
    """Set dependencies from main app"""
    global _session_factory, _search_providers, _auto_download_task_func
    _session_factory = session_factory
    _search_providers = search_providers
    _auto_download_task_func = auto_download_task


@router.post(
    "/periodicals/track",
    summary="Start tracking a periodical",
    description="Begin tracking a magazine, comic, or newspaper for automatic downloads.",
    responses={
        200: {
            "description": "Tracking started successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Started tracking Wired",
                        "tracking_id": 1,
                    }
                }
            },
        },
        400: {"description": "Invalid input", "model": APIError},
        500: {"description": "Failed to start tracking", "model": APIError},
    },
)
async def start_tracking_periodical(
    title: str = Query(...),
    category: Optional[str] = Query(None),
    country: Optional[str] = Query(None),
    language: Optional[str] = Query("English"),
) -> Dict[str, Any]:
    """Start tracking a periodical"""
    try:
        if not title or len(title.strip()) < 2:
            raise HTTPException(status_code=400, detail="Title must be at least 2 characters")

        olid = title.lower().replace(" ", "_").replace("-", "_")
        db_session = _session_factory()
        try:
            existing = db_session.query(MagazineTracking).filter(MagazineTracking.olid == olid).first()
            if existing:
                return {
                    "success": False,
                    "message": f"Already tracking '{title}'",
                    "tracking_id": existing.id,
                }

            tracking = MagazineTracking(
                olid=olid,
                title=title.strip(),
                category=category.strip() if category else None,
                language=language.strip() if language else "English",
                track_all_editions=False,
                selected_editions={},
                selected_years=[],
                last_metadata_update=datetime.now(UTC),
            )
            db_session.add(tracking)
            db_session.commit()

            logger.info(f"Started tracking periodical: {title}")
            return {
                "success": True,
                "tracking_id": tracking.id,
                "message": f"Started tracking '{title}'",
                "olid": olid,
            }
        finally:
            db_session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error tracking periodical: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error tracking periodical: {str(e)}")


@router.get(
    "/periodicals/tracked",
    summary="List tracked periodicals",
    description="Get a paginated list of all periodicals currently being tracked.",
    responses={
        200: {
            "description": "List retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "tracked": [{"id": 1, "title": "Wired", "publisher": "Condé Nast"}],
                        "total": 1,
                    }
                }
            },
        },
        500: {"description": "Failed to retrieve tracking list", "model": APIError},
    },
)
async def list_tracked_periodicals(skip: int = 0, limit: int = 50) -> Dict[str, Any]:
    """List all tracked periodicals"""
    try:
        db_session = _session_factory()
        try:
            tracked = db_session.query(MagazineTracking).offset(skip).limit(limit).all()
            total = db_session.query(MagazineTracking).count()

            return {
                "success": True,
                "tracked": [
                    {
                        "id": m.id,
                        "olid": m.olid,
                        "title": m.title,
                        "category": m.category,
                        "language": m.language,
                        "track_all_editions": m.track_all_editions,
                        "created_at": (m.created_at.isoformat() if m.created_at else None),
                    }
                    for m in tracked
                ],
                "total": total,
                "skip": skip,
                "limit": limit,
            }
        finally:
            db_session.close()
    except Exception as e:
        logger.error(f"Error listing tracked periodicals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/periodicals/tracked/{tracking_id}/search-issues")
async def search_tracked_periodical_issues(tracking_id: int) -> Dict[str, Any]:
    """Search for all issues of a tracked periodical"""
    try:
        db_session = _session_factory()
        try:
            tracking = db_session.query(MagazineTracking).filter(MagazineTracking.id == tracking_id).first()
            if not tracking:
                raise HTTPException(status_code=404, detail="Tracked magazine not found")

            if not _search_providers:
                raise HTTPException(status_code=503, detail="No search providers configured")

            all_results = []
            for provider in _search_providers:
                try:
                    results = provider.search(tracking.title)
                    all_results.extend(results)
                except Exception as e:
                    logger.warning(f"Provider {provider.__class__.__name__} error: {e}")

            if all_results:
                result_dicts = []
                for result in all_results:
                    try:
                        db_result = DBSearchResult(
                            provider=result.provider,
                            query=tracking.title,
                            title=result.title,
                            url=result.url,
                            publication_date=result.publication_date,
                            raw_metadata=result.raw_metadata or {},
                        )
                        db_session.add(db_result)
                        result_dicts.append(
                            {
                                "title": result.title,
                                "url": result.url,
                                "provider": result.provider,
                                "publication_date": (
                                    result.publication_date.isoformat() if result.publication_date else None
                                ),
                                "metadata": result.raw_metadata or {},
                            }
                        )
                    except Exception as e:
                        logger.warning(f"Error saving search result: {e}")

                db_session.commit()
                return {
                    "success": True,
                    "magazine": tracking.title,
                    "tracking_id": tracking.id,
                    "results": result_dicts,
                    "count": len(result_dicts),
                }
            else:
                return {
                    "success": False,
                    "magazine": tracking.title,
                    "tracking_id": tracking.id,
                    "message": f"No issues found for '{tracking.title}'",
                    "results": [],
                    "count": 0,
                }
        finally:
            db_session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching tracked periodical issues: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/periodicals/tracking/save")
async def save_tracking_preferences(
    request: TrackingPreferencesRequest,
) -> Dict[str, Any]:
    """Save magazine tracking preferences"""
    try:
        db_session = _session_factory()
        try:
            olid = request.olid or request.title.lower().replace(" ", "_").replace("-", "_")
            existing = db_session.query(MagazineTracking).filter(MagazineTracking.olid == olid).first()

            if existing:
                existing.title = request.title
                existing.category = getattr(request, 'category', None)
                existing.language = getattr(request, 'language', 'English')
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
                    category=getattr(request, 'category', None),
                    language=getattr(request, 'language', 'English'),
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

            # Trigger immediate auto-download check if tracking settings enabled
            if _auto_download_task_func and (
                tracking.track_all_editions
                or tracking.track_new_only
                or (tracking.selected_editions and any(tracking.selected_editions.values()))
            ):
                import asyncio

                try:
                    asyncio.create_task(_auto_download_task_func())
                    logger.info(f"Triggered immediate auto-download check after saving tracking for '{tracking.title}'")
                except Exception as e:
                    logger.warning(f"Could not trigger immediate auto-download: {e}")

            return {
                "success": True,
                "tracking_id": tracking.id,
                "message": f"Tracking preferences saved for '{request.title}'",
                "track_all_editions": tracking.track_all_editions,
                "selected_count": len([v for v in tracking.selected_editions.values() if v]),
            }
        finally:
            db_session.close()
    except Exception as e:
        logger.error(f"Save tracking preferences error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/periodicals/tracking")
async def list_tracked_magazines(
    skip: int = 0, limit: int = 50, sort_by: str = "title", sort_order: str = "asc"
) -> Dict[str, Any]:
    """List all currently tracked magazines"""
    try:
        db_session = _session_factory()
        try:
            is_descending = sort_order.lower() == "desc"
            query = db_session.query(MagazineTracking)

            if sort_by == "category":
                sort_expr = MagazineTracking.category.desc() if is_descending else MagazineTracking.category.asc()
                query = query.order_by(sort_expr, MagazineTracking.title.asc())
            elif sort_by == "tracking_mode":
                if is_descending:
                    query = query.order_by(
                        MagazineTracking.track_all_editions.asc(),
                        MagazineTracking.track_new_only.asc(),
                        MagazineTracking.title.desc(),
                    )
                else:
                    query = query.order_by(
                        MagazineTracking.track_all_editions.desc(),
                        MagazineTracking.track_new_only.desc(),
                        MagazineTracking.title.asc(),
                    )
            else:
                sort_expr = MagazineTracking.title.desc() if is_descending else MagazineTracking.title.asc()
                query = query.order_by(sort_expr)

            tracked = query.offset(skip).limit(limit).all()
            total = db_session.query(MagazineTracking).count()

            return {
                "success": True,
                "tracked_magazines": [
                    {
                        "id": t.id,
                        "olid": t.olid,
                        "title": t.title,
                        "category": t.category,
                        "language": t.language,
                        "track_all_editions": t.track_all_editions,
                        "track_new_only": t.track_new_only,
                        "selected_count": (
                            len([v for v in t.selected_editions.values() if v]) if t.selected_editions else 0
                        ),
                        "total_known": t.total_editions_known,
                        "created_at": (t.created_at.isoformat() if t.created_at else None),
                    }
                    for t in tracked
                ],
                "total": total,
                "skip": skip,
                "limit": limit,
            }
        finally:
            db_session.close()
    except Exception as e:
        logger.error(f"List tracked magazines error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/periodicals/tracking/{tracking_id}")
async def get_tracking_details(tracking_id: int) -> Dict[str, Any]:
    """Get detailed tracking information for a specific magazine"""
    try:
        db_session = _session_factory()
        try:
            tracking = db_session.query(MagazineTracking).filter(MagazineTracking.id == tracking_id).first()
            if not tracking:
                raise HTTPException(status_code=404, detail="Tracking record not found")

            return {
                "success": True,
                "tracking": {
                    "id": tracking.id,
                    "olid": tracking.olid,
                    "title": tracking.title,
                    "category": tracking.category,
                    "language": tracking.language,
                    "download_category": tracking.download_category,
                    "first_publish_year": tracking.first_publish_year,
                    "total_editions_known": tracking.total_editions_known,
                    "track_all_editions": tracking.track_all_editions,
                    "track_new_only": tracking.track_new_only,
                    "delete_from_client_on_completion": tracking.delete_from_client_on_completion,
                    "selected_editions": tracking.selected_editions,
                    "selected_years": tracking.selected_years,
                    "metadata": tracking.periodical_metadata,
                    "last_metadata_update": (
                        tracking.last_metadata_update.isoformat() if tracking.last_metadata_update else None
                    ),
                    "created_at": (tracking.created_at.isoformat() if tracking.created_at else None),
                },
            }
        finally:
            db_session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get tracking details error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _reorganize_magazine_files(
    magazine,
    new_title: str,
    organize_base_dir: Path,
    category_prefix: str = "_"
) -> Tuple[Optional[str], Optional[str]]:
    """
    Reorganize magazine files to match new title structure.

    Args:
        magazine: Magazine database object
        new_title: New title to use for folder organization
        organize_base_dir: Base directory for organized files
        category_prefix: Prefix for category folders (default: "_")

    Returns:
        Tuple of (new_pdf_path, new_cover_path) or (None, None) if failed
    """
    try:
        old_pdf_path = Path(magazine.file_path)
        old_cover_path = Path(magazine.cover_path) if magazine.cover_path else None

        # Extract metadata from current path structure
        category = magazine.extra_metadata.get("category", "Magazines") if magazine.extra_metadata else "Magazines"
        language = magazine.language or "English"
        issue_date = magazine.issue_date

        # Build new path structure
        safe_title = sanitize_filename(new_title)
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
            shutil.move(str(old_pdf_path), str(new_pdf_path))
            logger.info(f"Moved PDF: {old_pdf_path} -> {new_pdf_path}")
        elif new_pdf_path == old_pdf_path:
            # File is already in correct location
            pass
        else:
            logger.warning(f"PDF file not found: {old_pdf_path}")
            return None, None

        # Move cover file if it exists
        if old_cover_path and old_cover_path.exists() and new_cover_path and new_cover_path != old_cover_path:
            shutil.move(str(old_cover_path), str(new_cover_path))
            logger.info(f"Moved cover: {old_cover_path} -> {new_cover_path}")

        return str(new_pdf_path), str(new_cover_path) if new_cover_path else None

    except Exception as e:
        logger.error(f"Error reorganizing magazine files: {e}", exc_info=True)
        return None, None


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
                        "magazines_moved": 5,
                        "submissions_moved": 10,
                        "files_reorganized": 5,
                    }
                }
            },
        },
        400: {"description": "Invalid input", "model": APIError},
        404: {"description": "Tracking record not found", "model": APIError},
        500: {"description": "Failed to merge tracking", "model": APIError},
    },
)
async def merge_tracking(target_id: int, source_ids: Dict[str, list[int]]) -> Dict[str, Any]:
    """
    Merge multiple tracking records into a single target record.

    Args:
        target_id: The tracking record to merge into (will be kept)
        source_ids: Dict with 'source_ids' key containing list of tracking IDs to merge from (will be deleted)

    Returns:
        Dict with merge results including counts of magazines and submissions moved
    """
    try:
        if not source_ids.get("source_ids"):
            raise HTTPException(status_code=400, detail="No source tracking IDs provided")

        source_id_list = source_ids["source_ids"]

        if target_id in source_id_list:
            raise HTTPException(status_code=400, detail="Target tracking ID cannot be in source list")

        db_session = _session_factory()
        try:
            from models.database import Magazine, DownloadSubmission

            # Get target tracking record
            target = db_session.query(MagazineTracking).filter(MagazineTracking.id == target_id).first()
            if not target:
                raise HTTPException(status_code=404, detail="Target tracking record not found")

            # Get source tracking records
            sources = db_session.query(MagazineTracking).filter(MagazineTracking.id.in_(source_id_list)).all()
            if len(sources) != len(source_id_list):
                raise HTTPException(status_code=404, detail="One or more source tracking records not found")

            magazines_moved = 0
            submissions_moved = 0
            files_reorganized = 0
            directories_to_cleanup = set()

            # Get organize directory from config or use default
            # This should match the structure used by FileOrganizer
            organize_base_dir = Path("./local/data").resolve()
            category_prefix = "_"

            # Move magazines from source to target
            for source in sources:
                # Update magazines to point to target tracking and normalize title
                magazines = db_session.query(Magazine).filter(Magazine.tracking_id == source.id).all()
                for magazine in magazines:
                    magazine.tracking_id = target.id

                    # Only update title if this is NOT a special edition
                    # Special editions need to keep their distinct title to be grouped separately
                    is_special = False
                    if magazine.extra_metadata and isinstance(magazine.extra_metadata, dict):
                        is_special = magazine.extra_metadata.get("special_edition") is not None

                    # Also check title using the is_special_edition function
                    if not is_special:
                        is_special = is_special_edition(magazine.title)

                    # Only normalize title and reorganize files for regular editions
                    if not is_special:
                        # Store old directory for cleanup
                        old_pdf_path = Path(magazine.file_path)
                        if old_pdf_path.exists():
                            directories_to_cleanup.add(old_pdf_path.parent)

                        # Reorganize files to match new title structure
                        new_pdf_path, new_cover_path = _reorganize_magazine_files(
                            magazine,
                            target.title,
                            organize_base_dir,
                            category_prefix
                        )

                        # Update database paths if reorganization succeeded
                        if new_pdf_path:
                            magazine.file_path = new_pdf_path
                            if new_cover_path:
                                magazine.cover_path = new_cover_path
                            files_reorganized += 1
                            logger.info(f"Reorganized files for: {magazine.title} ({magazine.issue_date.strftime('%b %Y')})")
                        else:
                            logger.warning(f"Failed to reorganize files for magazine ID {magazine.id}, keeping original paths")

                        # Update title after file operations
                        magazine.title = target.title

                    magazines_moved += 1

                # Update download submissions to point to target tracking
                submissions = (
                    db_session.query(DownloadSubmission).filter(DownloadSubmission.tracking_id == source.id).all()
                )
                for submission in submissions:
                    submission.tracking_id = target.id
                    submissions_moved += 1

                # Delete source tracking record
                db_session.delete(source)

            db_session.commit()

            # Clean up empty directories after successful commit
            for directory in directories_to_cleanup:
                if directory.exists():
                    _cleanup_empty_directories(directory, organize_base_dir)

            source_titles = [s.title for s in sources]
            logger.info(
                f"Merged {len(sources)} tracking records ({', '.join(source_titles)}) into '{target.title}' (ID: {target_id}). "
                f"Moved {magazines_moved} magazines, reorganized {files_reorganized} files."
            )

            return {
                "success": True,
                "message": f"Merged {len(sources)} tracking record{'s' if len(sources) > 1 else ''} into '{target.title}'",
                "magazines_moved": magazines_moved,
                "submissions_moved": submissions_moved,
                "files_reorganized": files_reorganized,
                "merged_titles": source_titles,
            }
        finally:
            db_session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error merging tracking records: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete(
    "/periodicals/tracking/{tracking_id}",
    summary="Stop tracking a periodical",
    description="Remove a periodical from the tracking list. This does not delete downloaded files.",
    responses={
        200: {
            "description": "Tracking stopped successfully",
            "content": {"application/json": {"example": {"success": True, "message": "Stopped tracking 'Wired'"}}},
        },
        404: {"description": "Tracking record not found", "model": APIError},
        500: {"description": "Failed to delete tracking", "model": APIError},
    },
)
async def delete_tracking(tracking_id: int) -> Dict[str, Any]:
    """Delete a magazine tracking record"""
    try:
        db_session = _session_factory()
        try:
            tracking = db_session.query(MagazineTracking).filter(MagazineTracking.id == tracking_id).first()
            if not tracking:
                raise HTTPException(status_code=404, detail="Tracking record not found")

            title = tracking.title
            db_session.delete(tracking)
            db_session.commit()

            logger.info(f"Deleted tracking for magazine: {title}")
            return {"success": True, "message": f"Stopped tracking '{title}'"}
        finally:
            db_session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting tracking: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/periodicals/tracking/{tracking_id}")
async def update_tracking(tracking_id: int, updates: dict) -> Dict[str, Any]:
    """Update magazine tracking record"""
    try:
        db_session = _session_factory()
        try:
            tracking = db_session.query(MagazineTracking).filter(MagazineTracking.id == tracking_id).first()
            if not tracking:
                raise HTTPException(status_code=404, detail="Tracking record not found")

            if "title" in updates:
                tracking.title = updates["title"]
            if "category" in updates:
                tracking.category = updates["category"]
            if "language" in updates:
                tracking.language = updates["language"]
            if "download_category" in updates:
                tracking.download_category = updates["download_category"]
            if "track_all_editions" in updates:
                tracking.track_all_editions = updates["track_all_editions"]
            if "track_new_only" in updates:
                tracking.track_new_only = updates["track_new_only"]
            if "delete_from_client_on_completion" in updates:
                tracking.delete_from_client_on_completion = updates["delete_from_client_on_completion"]

            db_session.commit()

            # Trigger immediate auto-download check if tracking settings changed
            if _auto_download_task_func and any(k in updates for k in ["track_all_editions", "track_new_only"]):
                import asyncio

                try:
                    asyncio.create_task(_auto_download_task_func())
                    logger.info(
                        f"Triggered immediate auto-download check after updating tracking for '{tracking.title}'"
                    )
                except Exception as e:
                    logger.warning(f"Could not trigger immediate auto-download: {e}")

            return {
                "success": True,
                "message": "Tracking updated successfully",
                "tracking": {
                    "id": tracking.id,
                    "title": tracking.title,
                    "track_all_editions": tracking.track_all_editions,
                    "track_new_only": tracking.track_new_only,
                    "delete_from_client_on_completion": tracking.delete_from_client_on_completion,
                },
            }
        finally:
            db_session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update tracking error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post(
    "/periodicals/tracking/{tracking_id}/editions/{edition_id}/track",
    summary="Track a single issue",
    description="Mark a specific edition/issue for tracking and automatic download.",
    responses={
        200: {
            "description": "Issue tracking updated",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "message": "Issue marked for tracking",
                        "edition_id": "OL123456M",
                        "tracked": True,
                    }
                }
            },
        },
        404: {"description": "Tracking record not found", "model": APIError},
        500: {"description": "Failed to update tracking", "model": APIError},
    },
)
async def track_single_issue(tracking_id: int, edition_id: str, track: bool = Query(True)) -> Dict[str, Any]:
    """Track or untrack a single issue/edition"""
    try:
        db_session = _session_factory()
        try:
            tracking = db_session.query(MagazineTracking).filter(MagazineTracking.id == tracking_id).first()
            if not tracking:
                raise HTTPException(status_code=404, detail="Tracking record not found")

            # Initialize selected_editions if None
            if tracking.selected_editions is None:
                tracking.selected_editions = {}

            # Update the selected_editions dictionary
            tracking.selected_editions[edition_id] = track

            # Mark the column as modified for SQLAlchemy to detect the change
            from sqlalchemy.orm.attributes import flag_modified

            flag_modified(tracking, "selected_editions")

            db_session.commit()

            # Trigger immediate auto-download check if an edition was marked for tracking
            if track and _auto_download_task_func:
                import asyncio

                try:
                    asyncio.create_task(_auto_download_task_func())
                    logger.info(f"Triggered immediate auto-download check after tracking edition {edition_id}")
                except Exception as e:
                    logger.warning(f"Could not trigger immediate auto-download: {e}")

            action = "marked for tracking" if track else "unmarked from tracking"
            logger.info(f"Issue {edition_id} {action} for periodical '{tracking.title}'")

            return {
                "success": True,
                "message": f"Issue {action}",
                "tracking_id": tracking.id,
                "edition_id": edition_id,
                "tracked": track,
                "total_selected": len([v for v in tracking.selected_editions.values() if v]),
            }
        finally:
            db_session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Track single issue error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
