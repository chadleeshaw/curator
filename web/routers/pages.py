"""
HTML page serving routes
"""

import json
import logging
from collections import defaultdict
from typing import Callable

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from core.utils import run_in_thread
from core.utils.db import with_db_session
from core.utils.error_handling import handle_api_errors
from core.utils.general import is_special_edition
from core.version import get_version_info
from models.database import Periodical

router = APIRouter(tags=["pages"])
logger = logging.getLogger(__name__)

# Global state (injected from main app)
_session_factory = None


def set_dependencies(session_factory: Callable) -> None:
    """Set dependencies from main app"""
    global _session_factory
    _session_factory = session_factory


@router.get("/api/version")
async def get_version():
    """Get application version information"""
    return JSONResponse(content=get_version_info())


@router.get("/")
async def root():
    """Serve main page"""
    return FileResponse("templates/index.html")


@router.get("/login.html")
async def login_page():
    """Serve login page"""
    return FileResponse("templates/login.html")


@router.get("/epub-reader")
async def epub_reader_page(id: int = Query(...)):
    """Serve EPUB reader page for a specific periodical"""
    return FileResponse("templates/epub-reader.html")


@router.get("/comic-reader")
async def comic_reader_page(id: int = Query(...)):
    """Serve Comic reader page for a specific CBZ/CBR periodical"""
    return FileResponse("templates/comic-reader.html")


@router.get("/pdf-reader")
async def pdf_reader_page(id: int = Query(...)):
    """Serve PDF reader page for a specific PDF periodical"""
    return FileResponse("templates/pdf-reader.html")


@router.get("/periodical")
@handle_api_errors("View periodical by ID", logger)
async def view_periodical_by_id(id: int = Query(...)):
    """View all published issues of a periodical by periodical ID"""

    def operation(db):
        from models.database import PeriodicalTracking

        # Query the periodical to get its title and tracking info
        periodical = db.query(Periodical).filter(Periodical.id == id).first()

        if not periodical:
            raise HTTPException(status_code=404, detail=f"Periodical with ID {id} not found")

        # Determine the title to display and how to query
        if periodical.tracking_id:
            # Use tracking title for display and query by tracking_id
            tracking = db.query(PeriodicalTracking).filter(PeriodicalTracking.id == periodical.tracking_id).first()
            display_title = tracking.title if tracking else periodical.title

            # Query all magazines with same tracking_id (includes special editions)
            periodicals = (
                db.query(Periodical)
                .filter(Periodical.tracking_id == periodical.tracking_id)
                .order_by(Periodical.issue_date.desc())
                .all()
            )
        else:
            # No tracking - use the magazine's own title
            display_title = periodical.title
            periodicals = (
                db.query(Periodical)
                .filter(Periodical.title == display_title)
                .order_by(Periodical.issue_date.desc())
                .all()
            )

        if not periodicals:
            raise HTTPException(
                status_code=404,
                detail=f"No periodicals found for '{display_title}'",
            )

        # Group periodicals by year
        periodicals_by_year = defaultdict(list)
        for p in periodicals:
            year = p.issue_date.year if p.issue_date else "Unknown"
            periodicals_by_year[year].append(
                {
                    "id": p.id,
                    "title": p.title,
                    "issue_date": (p.issue_date.date().isoformat() if p.issue_date else None),
                    "cover_path": p.cover_path,
                    "file_path": p.file_path,
                }
            )

        # Sort years in descending order
        sorted_years = sorted(periodicals_by_year.keys(), reverse=True)

        return display_title, sorted_years, periodicals_by_year

    display_title, sorted_years, periodicals_by_year = await with_db_session(_session_factory, operation)

    # Read the periodical template
    try:
        with open("templates/periodical.html", "r") as f:
            template_content = f.read()
    except FileNotFoundError:
        logger.error("periodical.html template not found")
        raise HTTPException(status_code=500, detail="Periodical template not found")

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
    # For JSON in HTML attributes, escape quotes properly
    years_json = json.dumps(years_data).replace('"', "&quot;")

    html_content = template_content.replace("{{PERIODICAL_TITLE}}", display_title)
    html_content = html_content.replace("{{YEARS_DATA}}", years_json)
    html_content = html_content.replace("{{SPECIAL_EDITIONS_DATA}}", "[]")

    return HTMLResponse(content=html_content)


@router.get("/periodicals/{periodical_title}")
@handle_api_errors("View periodical", logger)
async def view_periodical(periodical_title: str, language: str = Query(None), tracking_id: int = Query(None)):
    """View all published issues of a periodical organized by year"""

    def operation(db):
        from models.database import PeriodicalTracking

        # Determine the actual tracking title to display
        display_title = periodical_title

        # If tracking_id is provided, query by that (includes merged items)
        if tracking_id:
            query = db.query(Periodical).filter(Periodical.tracking_id == tracking_id)
            # Get the tracking title for display
            tracking = db.query(PeriodicalTracking).filter(PeriodicalTracking.id == tracking_id).first()
            if tracking:
                display_title = tracking.title
        else:
            # Try to find a tracking record by title first
            tracking = db.query(PeriodicalTracking).filter(PeriodicalTracking.title == periodical_title).first()

            if tracking:
                # Query all magazines with this tracking_id
                query = db.query(Periodical).filter(Periodical.tracking_id == tracking.id)
                display_title = tracking.title
            else:
                # No tracking found by that title - try querying magazines by title
                # and if they have a tracking_id, use that tracking title instead
                query = db.query(Periodical).filter(Periodical.title == periodical_title)
                sample_mag = query.first()
                if sample_mag and sample_mag.tracking_id:
                    # This magazine has tracking - use the tracking title
                    tracking = (
                        db.query(PeriodicalTracking).filter(PeriodicalTracking.id == sample_mag.tracking_id).first()
                    )
                    if tracking:
                        display_title = tracking.title
                        # Re-query using tracking_id to get all issues
                        query = db.query(Periodical).filter(Periodical.tracking_id == tracking.id)

        # Add language filter if provided
        if language:
            query = query.filter(Periodical.language == language)

        periodicals = query.order_by(Periodical.issue_date.desc()).all()

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
                "issue_date": (p.issue_date.date().isoformat() if p.issue_date else None),
                "cover_path": p.cover_path,
                "file_path": p.file_path,
                "extra_metadata": p.extra_metadata or {},
            }

            # Check if this is a special edition by checking derived_metadata first, then extra_metadata, then title
            is_special = False
            special_edition_value = None

            # Check derived_metadata first (new location)
            if p.derived_metadata and isinstance(p.derived_metadata, dict):
                special_data = p.derived_metadata.get("special_edition")
                if special_data:
                    if isinstance(special_data, dict):
                        special_edition_value = special_data.get("value")
                    else:
                        special_edition_value = special_data
                    if special_edition_value:
                        is_special = True

            # Fallback to extra_metadata (legacy location)
            if not is_special and p.extra_metadata and isinstance(p.extra_metadata, dict):
                special_edition_value = p.extra_metadata.get("special_edition")
                if special_edition_value:
                    is_special = True

            # Store special edition name if found
            if is_special and special_edition_value:
                if isinstance(special_edition_value, str):
                    periodical_data["special_edition_name"] = special_edition_value
                else:
                    periodical_data["special_edition_name"] = ""

            # Fallback to title pattern matching
            if not is_special and is_special_edition(p.title):
                is_special = True

            if is_special:
                special_editions.append(periodical_data)
            else:
                year = p.issue_date.year if p.issue_date else "Unknown"
                periodicals_by_year[year].append(periodical_data)

        # Sort years in descending order
        sorted_years = sorted(periodicals_by_year.keys(), reverse=True)

        return (
            display_title,
            sorted_years,
            periodicals_by_year,
            special_editions,
        )

    (
        display_title,
        sorted_years,
        periodicals_by_year,
        special_editions,
    ) = await with_db_session(_session_factory, operation)

    # Read the periodical template
    try:
        with open("templates/periodical.html", "r") as f:
            template_content = f.read()
    except FileNotFoundError:
        logger.error("periodical.html template not found")
        raise HTTPException(status_code=500, detail="Periodical template not found")

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

    # For JSON in HTML attributes, escape quotes properly
    years_json = json.dumps(years_data).replace('"', "&quot;")
    special_editions_json = json.dumps(special_editions_data).replace('"', "&quot;")

    html_content = template_content.replace("{{PERIODICAL_TITLE}}", display_title)
    html_content = html_content.replace("{{YEARS_DATA}}", years_json)
    html_content = html_content.replace("{{SPECIAL_EDITIONS_DATA}}", special_editions_json)

    return HTMLResponse(content=html_content)
