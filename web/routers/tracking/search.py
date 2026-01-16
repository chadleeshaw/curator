"""
Tracking routes - Search functionality
"""

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from fastapi import HTTPException, Query

from core.constants.errors import ErrorMessages
from core.parsers import sanitize_filename
from core.utils.general import (
    is_special_edition,
    generate_olid,
    cleanup_empty_directories,
)
from models.database import MagazineTracking
from models.database import SearchResult as DBSearchResult
from web.schemas import APIError, TrackingPreferencesRequest
from core.utils import run_in_thread
from . import _shared

# Access global state via _shared module to get current values
router = _shared.router
logger = _shared.logger


@router.get("/periodicals/tracked/{tracking_id}/search-issues")
async def search_tracked_periodical_issues(tracking_id: int) -> Dict[str, Any]:
    """Search for all issues of a tracked periodical"""
    try:

        def _search():
            db_session = _shared._session_factory()
            try:
                tracking = db_session.query(MagazineTracking).filter(MagazineTracking.id == tracking_id).first()
                if not tracking:
                    raise HTTPException(status_code=404, detail="Tracked magazine not found")

                if not _shared._search_providers:
                    raise HTTPException(
                        status_code=503,
                        detail=ErrorMessages.SEARCH_PROVIDERS_UNAVAILABLE,
                    )

                all_results = []
                for provider in _shared._search_providers:
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

        return await run_in_thread(_search)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching tracked periodical issues: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
