"""
HTML page serving routes
"""

import json
import logging
from collections import defaultdict

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse

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
            # Query the periodical to get its title
            periodical = db_session.query(Magazine).filter(Magazine.id == id).first()

            if not periodical:
                raise HTTPException(status_code=404, detail=f"Periodical with ID {id} not found")

            # Redirect to the title-based route
            periodical_title = periodical.title

            # Query all periodicals with this title
            periodicals = (
                db_session.query(Magazine)
                .filter(Magazine.title == periodical_title)
                .order_by(Magazine.issue_date.desc())
                .all()
            )

            if not periodicals:
                raise HTTPException(status_code=404, detail=f"No periodicals found for '{periodical_title}'")

            # Group periodicals by year
            periodicals_by_year = defaultdict(list)
            for p in periodicals:
                year = p.issue_date.year if p.issue_date else "Unknown"
                periodicals_by_year[year].append(
                    {
                        "id": p.id,
                        "title": p.title,
                        "issue_date": p.issue_date.isoformat() if p.issue_date else None,
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
async def view_periodical(periodical_title: str):
    """View all published issues of a periodical organized by year"""
    try:
        db_session = _session_factory()
        try:
            # Query all periodicals with this title
            periodicals = (
                db_session.query(Magazine)
                .filter(Magazine.title == periodical_title)
                .order_by(Magazine.issue_date.desc())
                .all()
            )

            if not periodicals:
                raise HTTPException(status_code=404, detail=f"No periodicals found for '{periodical_title}'")

            # Group periodicals by year
            periodicals_by_year = defaultdict(list)
            for p in periodicals:
                year = p.issue_date.year if p.issue_date else "Unknown"
                periodicals_by_year[year].append(
                    {
                        "id": p.id,
                        "title": p.title,
                        "issue_date": p.issue_date.isoformat() if p.issue_date else None,
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
                        }
                    )
                years_data.append({"year": year, "issues": year_issues})

            # Replace template variables
            import html
            html_content = template_content.replace("{{PERIODICAL_TITLE}}", periodical_title)
            html_content = html_content.replace("{{YEARS_DATA}}", html.escape(json.dumps(years_data)))

            return HTMLResponse(content=html_content)
        finally:
            db_session.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"View periodical error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
