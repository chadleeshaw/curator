"""
Periodical tracking routes
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

from models.database import MagazineTracking
from models.database import SearchResult as DBSearchResult
from web.schemas import TrackingPreferencesRequest

router = APIRouter(prefix="/api", tags=["tracking"])
logger = logging.getLogger(__name__)

# Global state (injected from main app)
_session_factory = None
_search_providers = None


def set_dependencies(session_factory, search_providers):
    """Set dependencies from main app"""
    global _session_factory, _search_providers
    _session_factory = session_factory
    _search_providers = search_providers


@router.post("/periodicals/track")
async def start_tracking_periodical(
    title: str = Query(...),
    publisher: Optional[str] = Query(None),
    issn: Optional[str] = Query(None),
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
                publisher=publisher.strip() if publisher else None,
                issn=issn.strip() if issn else None,
                track_all_editions=False,
                selected_editions={},
                selected_years=[],
                last_metadata_update=datetime.utcnow(),
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


@router.get("/periodicals/tracked")
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
                        "publisher": m.publisher,
                        "issn": m.issn,
                        "track_all_editions": m.track_all_editions,
                        "created_at": m.created_at.isoformat() if m.created_at else None,
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
                        result_dicts.append({
                            "title": result.title,
                            "url": result.url,
                            "provider": result.provider,
                            "publication_date": result.publication_date.isoformat() if result.publication_date else None,
                            "metadata": result.raw_metadata or {},
                        })
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
async def save_tracking_preferences(request: TrackingPreferencesRequest) -> Dict[str, Any]:
    """Save magazine tracking preferences"""
    try:
        db_session = _session_factory()
        try:
            olid = request.olid or request.title.lower().replace(" ", "_").replace("-", "_")
            existing = db_session.query(MagazineTracking).filter(MagazineTracking.olid == olid).first()

            if existing:
                existing.title = request.title
                existing.publisher = request.publisher
                existing.issn = request.issn
                existing.first_publish_year = request.first_publish_year
                existing.track_all_editions = request.track_all_editions
                existing.track_new_only = request.track_new_only
                existing.selected_editions = request.selected_editions
                existing.selected_years = request.selected_years
                existing.periodical_metadata = request.metadata
                existing.last_metadata_update = datetime.utcnow()
                tracking = existing
            else:
                tracking = MagazineTracking(
                    olid=olid,
                    title=request.title,
                    publisher=request.publisher,
                    issn=request.issn,
                    first_publish_year=request.first_publish_year,
                    track_all_editions=request.track_all_editions,
                    track_new_only=request.track_new_only,
                    selected_editions=request.selected_editions,
                    selected_years=request.selected_years,
                    periodical_metadata=request.metadata,
                    last_metadata_update=datetime.utcnow(),
                )
                db_session.add(tracking)

            db_session.commit()
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
async def list_tracked_magazines(skip: int = 0, limit: int = 50, sort_by: str = "title", sort_order: str = "asc") -> Dict[str, Any]:
    """List all currently tracked magazines"""
    try:
        db_session = _session_factory()
        try:
            is_descending = sort_order.lower() == "desc"
            query = db_session.query(MagazineTracking)

            if sort_by == "publisher":
                sort_expr = MagazineTracking.publisher.desc() if is_descending else MagazineTracking.publisher.asc()
                query = query.order_by(sort_expr, MagazineTracking.title.asc())
            elif sort_by == "tracking_mode":
                if is_descending:
                    query = query.order_by(
                        MagazineTracking.track_all_editions.asc(),
                        MagazineTracking.track_new_only.asc(),
                        MagazineTracking.title.desc()
                    )
                else:
                    query = query.order_by(
                        MagazineTracking.track_all_editions.desc(),
                        MagazineTracking.track_new_only.desc(),
                        MagazineTracking.title.asc()
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
                        "publisher": t.publisher,
                        "issn": t.issn,
                        "track_all_editions": t.track_all_editions,
                        "track_new_only": t.track_new_only,
                        "selected_count": len([v for v in t.selected_editions.values() if v]) if t.selected_editions else 0,
                        "total_known": t.total_editions_known,
                        "created_at": t.created_at.isoformat() if t.created_at else None,
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
                    "publisher": tracking.publisher,
                    "issn": tracking.issn,
                    "first_publish_year": tracking.first_publish_year,
                    "total_editions_known": tracking.total_editions_known,
                    "track_all_editions": tracking.track_all_editions,
                    "selected_editions": tracking.selected_editions,
                    "selected_years": tracking.selected_years,
                    "metadata": tracking.periodical_metadata,
                    "last_metadata_update": tracking.last_metadata_update.isoformat() if tracking.last_metadata_update else None,
                    "created_at": tracking.created_at.isoformat() if tracking.created_at else None,
                },
            }
        finally:
            db_session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get tracking details error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/periodicals/tracking/{tracking_id}")
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
            if "publisher" in updates:
                tracking.publisher = updates["publisher"]
            if "issn" in updates:
                tracking.issn = updates["issn"]
            if "track_all_editions" in updates:
                tracking.track_all_editions = updates["track_all_editions"]

            db_session.commit()
            return {
                "success": True,
                "message": "Tracking updated successfully",
                "tracking": {
                    "id": tracking.id,
                    "title": tracking.title,
                    "publisher": tracking.publisher,
                    "issn": tracking.issn,
                    "track_all_editions": tracking.track_all_editions,
                },
            }
        finally:
            db_session.close()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Update tracking error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
