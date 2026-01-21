"""
Tracking routes - CRUD operations
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException, Query

from core.constants.category import DEFAULT_CATEGORY
from core.constants.errors import ErrorMessages
from core.parsers import sanitize_filename
from core.utils.general import (
    generate_olid,
)
from models.database import PeriodicalTracking
from web.schemas import APIError
from core.utils import run_in_thread
from . import _shared

# Access global state via _shared module to get current values
router = _shared.router
logger = _shared.logger

import shutil


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

        olid = generate_olid(title)

        def _create():
            db_session = _shared._session_factory()
            try:
                existing = db_session.query(PeriodicalTracking).filter(PeriodicalTracking.olid == olid).first()
                if existing:
                    return {
                        "success": False,
                        "message": f"Already tracking '{title}'",
                        "tracking_id": existing.id,
                    }

                tracking = PeriodicalTracking(
                    olid=olid,
                    title=title.strip(),
                    category=category.strip() if category else None,
                    language=language.strip() if language else "English",
                    country=country.strip() if country else None,
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

        return await run_in_thread(_create)
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

        def _query():
            db_session = _shared._session_factory()
            try:
                tracked = db_session.query(PeriodicalTracking).offset(skip).limit(limit).all()
                total = db_session.query(PeriodicalTracking).count()

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

        return await run_in_thread(_query)
    except Exception as e:
        logger.error(f"Error listing tracked periodicals: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/periodicals/tracking")
async def list_tracked_magazines(
    skip: int = 0, limit: int = 50, sort_by: str = "title", sort_order: str = "asc"
) -> Dict[str, Any]:
    """List all currently tracked magazines"""
    try:

        def _query():
            db_session = _shared._session_factory()
            try:
                is_descending = sort_order.lower() == "desc"
                query = db_session.query(PeriodicalTracking)

                if sort_by == "category":
                    sort_expr = (
                        PeriodicalTracking.category.desc() if is_descending else PeriodicalTracking.category.asc()
                    )
                    query = query.order_by(sort_expr, PeriodicalTracking.title.asc())
                elif sort_by == "tracking_mode":
                    if is_descending:
                        query = query.order_by(
                            PeriodicalTracking.track_all_editions.asc(),
                            PeriodicalTracking.track_new_only.asc(),
                        )
                    else:
                        query = query.order_by(
                            PeriodicalTracking.track_all_editions.desc(),
                            PeriodicalTracking.track_new_only.desc(),
                        )
                else:
                    sort_expr = PeriodicalTracking.title.desc() if is_descending else PeriodicalTracking.title.asc()
                    query = query.order_by(sort_expr)

                tracked = query.offset(skip).limit(limit).all()
                total = db_session.query(PeriodicalTracking).count()

                # Compute library count and failed download count for each tracked periodical
                from models.database import (
                    Periodical,
                    DiscoveredIssue,
                    DownloadSubmission,
                )

                tracked_list = []
                for t in tracked:
                    library_count = db_session.query(Periodical).filter(Periodical.tracking_id == t.id).count()

                    # Count failed downloads from both sources for backward compatibility:
                    # 1. New Issue Discovery system (canonical going forward)
                    # 2. Legacy DownloadSubmission system (for historical failures)
                    discovered_failed = (
                        db_session.query(DiscoveredIssue)
                        .filter(
                            DiscoveredIssue.tracking_id == t.id,
                            DiscoveredIssue.download_status.in_(["failed", "permanently_failed"]),
                        )
                        .count()
                    )

                    legacy_failed = (
                        db_session.query(DownloadSubmission)
                        .filter(
                            DownloadSubmission.tracking_id == t.id,
                            DownloadSubmission.status == DownloadSubmission.StatusEnum.FAILED,
                        )
                        .count()
                    )

                    # Show total of both systems (UI will query both)
                    failed_count = discovered_failed + legacy_failed

                    tracked_list.append(
                        {
                            "id": t.id,
                            "olid": t.olid,
                            "title": t.title,
                            "category": t.category,
                            "language": t.language,
                            "country": t.country,
                            "track_all_editions": t.track_all_editions,
                            "track_new_only": t.track_new_only,
                            "selected_count": (
                                len([v for v in t.selected_editions.values() if v]) if t.selected_editions else 0
                            ),
                            "total_known": t.total_editions_known,
                            "library_count": library_count,
                            "failed_count": failed_count,
                            "created_at": (t.created_at.isoformat() if t.created_at else None),
                        }
                    )

                return {
                    "success": True,
                    "tracked_magazines": tracked_list,
                    "total": total,
                    "skip": skip,
                    "limit": limit,
                }
            finally:
                db_session.close()

        return await run_in_thread(_query)
    except Exception as e:
        logger.error(f"List tracked magazines error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/periodicals/tracking/{tracking_id}")
async def get_tracking_details(tracking_id: int) -> Dict[str, Any]:
    """Get detailed tracking information for a specific magazine"""
    try:

        def _query():
            db_session = _shared._session_factory()
            try:
                tracking = db_session.query(PeriodicalTracking).filter(PeriodicalTracking.id == tracking_id).first()
                if not tracking:
                    raise HTTPException(status_code=404, detail=ErrorMessages.TRACKING_NOT_FOUND)

                return {
                    "success": True,
                    "tracking": {
                        "id": tracking.id,
                        "olid": tracking.olid,
                        "title": tracking.title,
                        "category": tracking.category,
                        "language": tracking.language,
                        "country": tracking.country,
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

        return await run_in_thread(_query)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get tracking details error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _reorganize_periodical_files(
    periodical, new_title: str, library_base_dir: Path, category_prefix: str = "_"
) -> Tuple[Optional[str], Optional[str]]:
    """
    Reorganize periodical files to match new title structure.

    Args:
        magazine: Periodical database object
        new_title: New title to use for folder organization
        library_base_dir: Base directory for organized files
        category_prefix: Prefix for category folders (default: "_")

    Returns:
        Tuple of (new_pdf_path, new_cover_path) or (None, None) if failed

    Raises:
        Exception: If file reorganization fails (caught and returns None, None)
    """
    try:
        old_pdf_path = Path(periodical.file_path)
        old_cover_path = Path(periodical.cover_path) if periodical.cover_path else None

        # Extract metadata from current path structure
        category = (
            periodical.extra_metadata.get("category", DEFAULT_CATEGORY)
            if periodical.extra_metadata
            else DEFAULT_CATEGORY
        )
        issue_date = periodical.issue_date

        # Build new path structure (without language folder)
        safe_title = sanitize_filename(new_title)
        month = issue_date.strftime("%B")
        year = issue_date.strftime("%Y")
        filename_base = f"{safe_title} - {month}{year}"

        category_with_prefix = f"{category_prefix}{category}"
        target_dir = library_base_dir / category_with_prefix / safe_title / year
        target_dir.mkdir(parents=True, exist_ok=True)

        new_pdf_path = target_dir / f"{filename_base}.pdf"
        new_cover_path = target_dir / f"{filename_base}.jpg" if old_cover_path else None

        # Handle filename conflicts by appending timestamp
        if new_pdf_path.exists() and new_pdf_path != old_pdf_path:
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
        logger.error(f"Error reorganizing periodical files: {e}", exc_info=True)
        return None, None


@router.delete(
    "/periodicals/tracking/{tracking_id}",
    summary="Stop tracking a periodical",
    description="Remove a periodical from the tracking list. This does not delete downloaded files.",
    responses={
        200: {
            "description": "Tracking stopped successfully",
            "content": {"application/json": {"example": {"success": True, "message": "Stopped tracking 'Wired'"}}},
        },
        404: {"description": ErrorMessages.TRACKING_NOT_FOUND, "model": APIError},
        500: {"description": "Failed to delete tracking", "model": APIError},
    },
)
async def delete_tracking(tracking_id: int) -> Dict[str, Any]:
    """Delete a magazine tracking record"""
    try:

        def _delete():
            db_session = _shared._session_factory()
            try:
                tracking = db_session.query(PeriodicalTracking).filter(PeriodicalTracking.id == tracking_id).first()
                if not tracking:
                    raise HTTPException(status_code=404, detail=ErrorMessages.TRACKING_NOT_FOUND)

                title = tracking.title
                db_session.delete(tracking)
                db_session.commit()

                logger.info(f"Deleted tracking for magazine: {title}")
                return {"success": True, "message": f"Stopped tracking '{title}'"}
            finally:
                db_session.close()

        return await run_in_thread(_delete)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting tracking: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
