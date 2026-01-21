"""
Reading progress tracking for periodicals
"""

from typing import Any, Dict, Optional

from fastapi import HTTPException
from pydantic import BaseModel

from core.constants.errors import ErrorMessages
from core.parsers import utc_now
from core.utils import run_in_thread
from models.database import Periodical, ReadingProgress

from . import _shared

router = _shared.router
logger = _shared.logger


class ProgressUpdate(BaseModel):
    """Schema for updating reading progress"""

    current_page: Optional[int] = None
    current_chapter: Optional[int] = None
    total_pages: Optional[int] = None


@router.get("/periodicals/{magazine_id}/progress")
async def get_progress(magazine_id: int) -> Dict[str, Any]:
    """
    Get reading progress for a periodical.

    Returns None if no progress has been saved yet.
    """
    try:

        def _db_operation():
            db_session = _shared._session_factory()
            try:
                # Verify magazine exists
                magazine = db_session.query(Periodical).filter(Periodical.id == magazine_id).first()
                if not magazine:
                    raise HTTPException(status_code=404, detail=ErrorMessages.MAGAZINE_NOT_FOUND)

                # Get progress
                progress = (
                    db_session.query(ReadingProgress).filter(ReadingProgress.periodical_id == magazine_id).first()
                )

                return progress.to_dict() if progress else None
            finally:
                db_session.close()

        result = await run_in_thread(_db_operation)
        return {"progress": result}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get progress error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/periodicals/{magazine_id}/progress")
async def update_progress(magazine_id: int, update: ProgressUpdate) -> Dict[str, Any]:
    """
    Update reading progress for a periodical.

    Creates a new progress record if one doesn't exist.
    """
    try:

        def _db_operation():
            db_session = _shared._session_factory()
            try:
                # Verify magazine exists
                magazine = db_session.query(Periodical).filter(Periodical.id == magazine_id).first()
                if not magazine:
                    raise HTTPException(status_code=404, detail=ErrorMessages.MAGAZINE_NOT_FOUND)

                # Get or create progress record
                progress = (
                    db_session.query(ReadingProgress).filter(ReadingProgress.periodical_id == magazine_id).first()
                )

                if not progress:
                    progress = ReadingProgress(magazine_id=magazine_id)
                    db_session.add(progress)

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

                db_session.commit()
                db_session.refresh(progress)

                return progress.to_dict()
            finally:
                db_session.close()

        result = await run_in_thread(_db_operation)
        return {"progress": result}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update progress error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/periodicals/{magazine_id}/progress")
async def delete_progress(magazine_id: int) -> Dict[str, str]:
    """
    Delete reading progress for a periodical.
    """
    try:

        def _db_operation():
            db_session = _shared._session_factory()
            try:
                # Verify magazine exists
                magazine = db_session.query(Periodical).filter(Periodical.id == magazine_id).first()
                if not magazine:
                    raise HTTPException(status_code=404, detail=ErrorMessages.MAGAZINE_NOT_FOUND)

                # Delete progress if exists
                progress = (
                    db_session.query(ReadingProgress).filter(ReadingProgress.periodical_id == magazine_id).first()
                )

                if progress:
                    db_session.delete(progress)
                    db_session.commit()

                return {"status": "success"}
            finally:
                db_session.close()

        result = await run_in_thread(_db_operation)
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete progress error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
