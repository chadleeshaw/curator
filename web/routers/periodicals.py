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
    List organized periodicals from library.

    Args:
        skip: Number of records to skip for pagination
        limit: Maximum number of records to return
        sort_by: Sort field - "title", "publisher", or "issue_date" (default: "title")
        sort_order: Sort direction - "asc" or "desc" (default: "asc")

    Returns:
        List of periodicals with their metadata
    """
    try:
        db_session = _session_factory()
        try:
            # Validate sort_order
            is_descending = sort_order.lower() == "desc"

            # Build query with sorting
            query = db_session.query(Magazine)

            if sort_by == "publisher":
                sort_expr = (
                    Magazine.publisher.desc()
                    if is_descending
                    else Magazine.publisher.asc()
                )
                query = query.order_by(sort_expr, Magazine.title.asc())
            elif sort_by == "issue_date":
                sort_expr = (
                    Magazine.issue_date.desc()
                    if is_descending
                    else Magazine.issue_date.asc()
                )
                query = query.order_by(sort_expr)
            else:  # Default to title
                sort_expr = (
                    Magazine.title.desc() if is_descending else Magazine.title.asc()
                )
                query = query.order_by(sort_expr)

            magazines = query.offset(skip).limit(limit).all()
            total = db_session.query(Magazine).count()

            return {
                "periodicals": [
                    {
                        "id": m.id,
                        "title": m.title,
                        "publisher": m.publisher,
                        "issue_date": (
                            m.issue_date.isoformat() if m.issue_date else None
                        ),
                        "file_path": m.file_path,
                        "cover_path": m.cover_path,
                        "metadata": m.extra_metadata,
                    }
                    for m in magazines
                ],
                "total": total,
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
                "publisher": magazine.publisher,
                "issue_date": (
                    magazine.issue_date.isoformat() if magazine.issue_date else None
                ),
                "file_path": magazine.file_path,
                "cover_path": magazine.cover_path,
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


@router.delete("/periodicals/{magazine_id}")
async def delete_periodical(
    magazine_id: int, delete_files: bool = False, remove_tracking: bool = False
) -> Dict[str, Any]:
    """
    Delete a periodical from the library

    Args:
        magazine_id: ID of periodical to delete
        delete_files: If True, also delete the PDF and cover files from disk. If False, only remove from database.
        remove_tracking: If True, also remove the tracking record for this periodical.
    """
    try:
        db_session = _session_factory()
        try:
            magazine = (
                db_session.query(Magazine).filter(Magazine.id == magazine_id).first()
            )

            if not magazine:
                raise HTTPException(status_code=404, detail="Magazine not found")

            # Store file paths and title for potential deletion
            pdf_path = Path(magazine.file_path)
            cover_path = Path(magazine.cover_path) if magazine.cover_path else None
            title = magazine.title

            # Delete database entry
            db_session.delete(magazine)
            db_session.commit()

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
                try:
                    if pdf_path.exists():
                        pdf_path.unlink()
                        logger.info(f"Deleted PDF file: {pdf_path}")
                except Exception as e:
                    logger.warning(f"Could not delete PDF file {pdf_path}: {e}")

                try:
                    if cover_path and cover_path.exists():
                        cover_path.unlink()
                        logger.info(f"Deleted cover file: {cover_path}")
                except Exception as e:
                    logger.warning(f"Could not delete cover file {cover_path}: {e}")

                logger.info(f"Deleted magazine and files from disk: {title}")
                message = f"Deleted '{title}' and files from disk"
                if remove_tracking:
                    message += " (tracking removed)"
                return {
                    "success": True,
                    "message": message,
                }
            else:
                logger.info(f"Deleted magazine from library (files retained): {title}")
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
