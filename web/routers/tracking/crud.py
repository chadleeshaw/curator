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
from core.utils.db import with_db_session
from core.utils.error_handling import handle_api_errors
from core.utils.general import (
    cleanup_empty_directories,
    generate_olid,
    is_special_edition,
)
from models.database import Periodical, PeriodicalTracking
from services.file_operations import reorganize_periodical_files
from web.schemas import APIError

from . import _shared

# Access global state via _shared module to get current values
router = _shared.router
logger = _shared.logger


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
@handle_api_errors("Start tracking periodical", logger)
async def start_tracking_periodical(
    title: str = Query(...),
    category: Optional[str] = Query(None),
    country: Optional[str] = Query(None),
    language: Optional[str] = Query("English"),
) -> Dict[str, Any]:
    """Start tracking a periodical"""
    if not title or len(title.strip()) < 2:
        raise HTTPException(status_code=400, detail="Title must be at least 2 characters")

    olid = generate_olid(title)

    def operation(db):
        existing = db.query(PeriodicalTracking).filter(PeriodicalTracking.olid == olid).first()
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
        db.add(tracking)
        db.commit()

        logger.info(f"Started tracking periodical: {title}")
        return {
            "success": True,
            "tracking_id": tracking.id,
            "message": f"Started tracking '{title}'",
            "olid": olid,
        }

    return await with_db_session(_shared._session_factory, operation)


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
@handle_api_errors("List tracked periodicals", logger)
async def list_tracked_periodicals(skip: int = 0, limit: int = 50) -> Dict[str, Any]:
    """List all tracked periodicals"""

    def operation(db):
        tracked = db.query(PeriodicalTracking).offset(skip).limit(limit).all()
        total = db.query(PeriodicalTracking).count()

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

    return await with_db_session(_shared._session_factory, operation)


@router.get("/periodicals/tracking")
@handle_api_errors("List tracked magazines", logger)
async def list_tracked_magazines(
    skip: int = 0, limit: int = 50, sort_by: str = "title", sort_order: str = "asc"
) -> Dict[str, Any]:
    """List all currently tracked magazines"""

    def operation(db):
        is_descending = sort_order.lower() == "desc"
        query = db.query(PeriodicalTracking)

        if sort_by == "category":
            sort_expr = PeriodicalTracking.category.desc() if is_descending else PeriodicalTracking.category.asc()
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
        total = db.query(PeriodicalTracking).count()

        # Compute library count and failed download count for each tracked periodical
        from models.database import (
            DiscoveredIssue,
            DownloadSubmission,
        )

        tracked_list = []
        for t in tracked:
            library_count = db.query(Periodical).filter(Periodical.tracking_id == t.id).count()

            # Count failed downloads from both sources for backward compatibility:
            # 1. New Issue Discovery system (canonical going forward)
            # 2. Legacy DownloadSubmission system (for historical failures)
            discovered_failed = (
                db.query(DiscoveredIssue)
                .filter(
                    DiscoveredIssue.tracking_id == t.id,
                    DiscoveredIssue.download_status.in_(["failed", "permanently_failed"]),
                )
                .count()
            )

            legacy_failed = (
                db.query(DownloadSubmission)
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

    return await with_db_session(_shared._session_factory, operation)


@router.get("/periodicals/tracking/{tracking_id}")
@handle_api_errors("Get tracking details", logger)
async def get_tracking_details(tracking_id: int) -> Dict[str, Any]:
    """Get detailed tracking information for a specific magazine"""

    def operation(db):
        tracking = db.query(PeriodicalTracking).filter(PeriodicalTracking.id == tracking_id).first()
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

    return await with_db_session(_shared._session_factory, operation)


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
@handle_api_errors("Delete tracking", logger)
async def delete_tracking(tracking_id: int) -> Dict[str, Any]:
    """Delete a magazine tracking record"""

    def operation(db):
        tracking = db.query(PeriodicalTracking).filter(PeriodicalTracking.id == tracking_id).first()
        if not tracking:
            raise HTTPException(status_code=404, detail=ErrorMessages.TRACKING_NOT_FOUND)

        title = tracking.title
        db.delete(tracking)
        db.commit()

        logger.info(f"Deleted tracking for magazine: {title}")
        return {"success": True, "message": f"Stopped tracking '{title}'"}

    return await with_db_session(_shared._session_factory, operation)
