"""
Tracking routes - Search functionality
"""

from typing import Any, Dict

from fastapi import HTTPException

from core.constants.errors import ErrorMessages
from core.utils.db import with_db_session
from core.utils.error_handling import handle_api_errors
from models.database import PeriodicalTracking
from models.database import SearchResult as DBSearchResult
from web.utils.responses import success_response, error_response

from . import _shared

# Access global state via _shared module to get current values
router = _shared.router
logger = _shared.logger


@router.get("/periodicals/tracked/{tracking_id}/search-issues")
@handle_api_errors("Search tracked periodical issues", logger)
async def search_tracked_periodical_issues(tracking_id: int) -> Dict[str, Any]:
    """Search for all issues of a tracked periodical"""

    def operation(db):
        tracking = db.query(PeriodicalTracking).filter(PeriodicalTracking.id == tracking_id).first()
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
                    db.add(db_result)
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

            db.commit()
            return success_response(
                None,
                magazine=tracking.title,
                tracking_id=tracking.id,
                results=result_dicts,
                count=len(result_dicts),
            )
        else:
            return error_response(
                f"No issues found for '{tracking.title}'",
                magazine=tracking.title,
                tracking_id=tracking.id,
                results=[],
                count=0,
            )

    return await with_db_session(_shared._session_factory, operation)
