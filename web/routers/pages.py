"""
HTML page serving routes
"""

import json
import logging
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse

from core.utils import is_special_edition
from models.database import Magazine

router = APIRouter(tags=["pages"])
logger = logging.getLogger(__name__)

# Global state (injected from main app)
_session_factory = None


def set_dependencies(session_factory):
    """Set dependencies from main app"""
    global _session_factory
    _session_factory = session_factory


@router.get("/")
async def root():
    """Serve main page"""
    return FileResponse("templates/index.html")


@router.get("/login.html")
async def login_page():
    """Serve login page"""
    return FileResponse("templates/login.html")


@router.get("/periodical")
async def view_periodical_by_id(id: int = Query(...)):
    """View all published issues of a periodical by periodical ID"""
    try:
        db_session = _session_factory()
        try:
            from models.database import MagazineTracking

            # Query the periodical to get its title and tracking info
            periodical = db_session.query(Magazine).filter(Magazine.id == id).first()

            if not periodical:
                raise HTTPException(
                    status_code=404, detail=f"Periodical with ID {id} not found"
                )

            # Determine the title to display and how to query
            if periodical.tracking_id:
                # Use tracking title for display and query by tracking_id
                tracking = db_session.query(MagazineTracking).filter(
                    MagazineTracking.id == periodical.tracking_id
                ).first()
                periodical_title = tracking.title if tracking else periodical.title

                # Query all magazines with same tracking_id (includes special editions)
                periodicals = (
                    db_session.query(Magazine)
                    .filter(Magazine.tracking_id == periodical.tracking_id)
                    .order_by(Magazine.issue_date.desc())
                    .all()
                )
            else:
                # No tracking - query by title
                periodical_title = periodical.title
                periodicals = (
                    db_session.query(Magazine)
                    .filter(Magazine.title == periodical_title)
                    .order_by(Magazine.issue_date.desc())
                    .all()
                )

            if not periodicals:
                raise HTTPException(
                    status_code=404,
                    detail=f"No periodicals found for '{periodical_title}'",
                )

            # Group periodicals by year
            periodicals_by_year = defaultdict(list)
            for p in periodicals:
                year = p.issue_date.year if p.issue_date else "Unknown"
                periodicals_by_year[year].append(
                    {
                        "id": p.id,
                        "title": p.title,
                        "issue_date": (
                            p.issue_date.isoformat() if p.issue_date else None
                        ),
                        "cover_path": p.cover_path,
                        "file_path": p.file_path,
                    }
                )

            # Sort years in descending order
            sorted_years = sorted(periodicals_by_year.keys(), reverse=True)

            # Read the periodical template
            try:
                with open("templates/periodical.html", "r") as f:
                    template_content = f.read()
            except FileNotFoundError:
                logger.error("periodical.html template not found")
                raise HTTPException(
                    status_code=500, detail="Periodical template not found"
                )

            # Build years data JSON
            years_data = []
            for year in sorted_years:
                year_issues = []
                for p in periodicals_by_year[year]:
                    year_issues.append(
                        {
                            "id": p["id"],
                            "title": p["title"],
                            "issue_date": p["issue_date"],
                            "cover_url": f"/api/periodicals/{p['id']}/cover",
                            "file_path": p["file_path"],
                        }
                    )

                years_data.append({"year": year, "issues": year_issues})

            # Replace template variables
            import html

            html_content = template_content.replace(
                "{{PERIODICAL_TITLE}}", periodical_title
            ).replace("{{YEARS_DATA}}", html.escape(json.dumps(years_data)))

            return HTMLResponse(content=html_content)

        finally:
            db_session.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"View periodical error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/periodicals/{periodical_title}")
async def view_periodical(periodical_title: str, language: str = Query(None), tracking_id: int = Query(None)):
    """View all published issues of a periodical organized by year"""
    try:
        db_session = _session_factory()
        try:
            from models.database import MagazineTracking

            # If tracking_id is provided, query by that (includes merged items)
            if tracking_id:
                query = db_session.query(Magazine).filter(Magazine.tracking_id == tracking_id)
            else:
                # Try to find a tracking record by title first
                tracking = db_session.query(MagazineTracking).filter(
                    MagazineTracking.title == periodical_title
                ).first()

                if tracking:
                    # Query all magazines with this tracking_id
                    query = db_session.query(Magazine).filter(Magazine.tracking_id == tracking.id)
                else:
                    # No tracking - query by title
                    query = db_session.query(Magazine).filter(Magazine.title == periodical_title)

            # Add language filter if provided
            if language:
                query = query.filter(Magazine.language == language)

            periodicals = query.order_by(Magazine.issue_date.desc()).all()

            if not periodicals:
                raise HTTPException(
                    status_code=404,
                    detail=f"No periodicals found for '{periodical_title}'",
                )

            # Group periodicals by year and separate special editions
            periodicals_by_year = defaultdict(list)
            special_editions = []

            for p in periodicals:
                periodical_data = {
                    "id": p.id,
                    "title": p.title,
                    "issue_date": (p.issue_date.isoformat() if p.issue_date else None),
                    "cover_path": p.cover_path,
                    "file_path": p.file_path,
                    "extra_metadata": p.extra_metadata or {},
                }

                # Check if this is a special edition by checking metadata first, then title
                is_special = False
                if p.extra_metadata and isinstance(p.extra_metadata, dict):
                    if "special_edition" in p.extra_metadata:
                        is_special = True
                        periodical_data["special_edition_name"] = p.extra_metadata.get(
                            "special_edition", ""
                        )

                if not is_special and is_special_edition(p.title):
                    is_special = True

                if is_special:
                    special_editions.append(periodical_data)
                else:
                    year = p.issue_date.year if p.issue_date else "Unknown"
                    periodicals_by_year[year].append(periodical_data)

            # Sort years in descending order
            sorted_years = sorted(periodicals_by_year.keys(), reverse=True)

            # Read the periodical template
            try:
                with open("templates/periodical.html", "r") as f:
                    template_content = f.read()
            except FileNotFoundError:
                logger.error("periodical.html template not found")
                raise HTTPException(
                    status_code=500, detail="Periodical template not found"
                )

            # Build special editions data
            special_editions_data = []
            if special_editions:
                for p in special_editions:
                    special_data = {
                        "id": p["id"],
                        "title": p["title"],
                        "issue_date": p["issue_date"],
                        "cover_url": f"/api/periodicals/{p['id']}/cover",
                    }
                    # Add special edition name if available
                    if "special_edition_name" in p:
                        special_data["special_edition_name"] = p["special_edition_name"]
                    special_editions_data.append(special_data)

            # Build years data JSON
            years_data = []
            for year in sorted_years:
                year_issues = []
                for p in periodicals_by_year[year]:
                    year_issues.append(
                        {
                            "id": p["id"],
                            "title": p["title"],
                            "issue_date": p["issue_date"],
                            "cover_url": f"/api/periodicals/{p['id']}/cover",
                        }
                    )
                years_data.append({"year": year, "issues": year_issues})

            # Replace template variables
            import html

            html_content = template_content.replace(
                "{{PERIODICAL_TITLE}}", periodical_title
            )
            html_content = html_content.replace(
                "{{YEARS_DATA}}", html.escape(json.dumps(years_data))
            )
            html_content = html_content.replace(
                "{{SPECIAL_EDITIONS_DATA}}",
                html.escape(json.dumps(special_editions_data)),
            )

            return HTMLResponse(content=html_content)
        finally:
            db_session.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"View periodical error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
