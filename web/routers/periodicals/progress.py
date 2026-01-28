"""
Reading progress tracking for periodicals
"""

from typing import Any, Dict, Optional

from pydantic import BaseModel

from core.parsers import utc_now
from core.utils.db import with_db_session
from core.utils.error_handling import handle_api_errors
from models.database import ReadingProgress

from . import _shared

router = _shared.router
logger = _shared.logger


class ProgressUpdate(BaseModel):
    """Schema for updating reading progress"""

    current_page: Optional[int] = None
    current_chapter: Optional[int] = None
    total_pages: Optional[int] = None


@router.get("/periodicals/{magazine_id}/progress")
@handle_api_errors("Get progress", logger)
async def get_progress(magazine_id: int) -> Dict[str, Any]:
    """
    Get reading progress for a periodical.

    Returns None if no progress has been saved yet.
    """

    def operation(db):
        # Verify magazine exists
        _shared.get_periodical_or_404(db, magazine_id)

        # Get progress
        progress = db.query(ReadingProgress).filter(ReadingProgress.periodical_id == magazine_id).first()

        return progress.to_dict() if progress else None

    result = await with_db_session(_shared._session_factory, operation)
    return {"progress": result}


@router.post("/periodicals/{magazine_id}/progress")
@handle_api_errors("Update progress", logger)
async def update_progress(magazine_id: int, update: ProgressUpdate) -> Dict[str, Any]:
    """
    Update reading progress for a periodical.

    Creates a new progress record if one doesn't exist.
    """

    def operation(db):
        # Verify magazine exists
        _shared.get_periodical_or_404(db, magazine_id)

        # Get or create progress record
        progress = db.query(ReadingProgress).filter(ReadingProgress.periodical_id == magazine_id).first()

        if not progress:
            progress = ReadingProgress(periodical_id=magazine_id)
            db.add(progress)

        # Update fields
        if update.current_page is not None:
            progress.current_page = update.current_page
        if update.current_chapter is not None:
            progress.current_chapter = update.current_chapter
        if update.total_pages is not None:
            progress.total_pages = update.total_pages

        # Calculate progress percentage
        if progress.total_pages and progress.total_pages > 0:
            current = progress.current_page if progress.current_page is not None else progress.current_chapter
            if current is not None:
                progress.progress_percent = int((current + 1) / progress.total_pages * 100)

        progress.last_read_at = utc_now()
        progress.updated_at = utc_now()

        db.commit()
        db.refresh(progress)

        return progress.to_dict()

    result = await with_db_session(_shared._session_factory, operation)
    return {"progress": result}


@router.delete("/periodicals/{magazine_id}/progress")
@handle_api_errors("Delete progress", logger)
async def delete_progress(magazine_id: int) -> Dict[str, str]:
    """
    Delete reading progress for a periodical.
    """

    def operation(db):
        # Verify magazine exists
        _shared.get_periodical_or_404(db, magazine_id)

        # Delete progress if exists
        progress = db.query(ReadingProgress).filter(ReadingProgress.periodical_id == magazine_id).first()

        if progress:
            db.delete(progress)
            db.commit()

        return {"status": "success"}

    result = await with_db_session(_shared._session_factory, operation)
    return result
