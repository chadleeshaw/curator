"""
Shared dependencies and state for periodicals router package
"""

import logging
from pathlib import Path
from typing import Callable, Optional, Tuple

from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session

from core.constants.category import CATEGORIES
from core.constants.date import MONTH_TO_NUMBER, NUMBER_TO_MONTH_ABBR
from core.constants.errors import ErrorMessages
from models.database import Periodical

router = APIRouter(prefix="/api", tags=["periodicals"])
logger = logging.getLogger(__name__)

# Global state (injected from main app)
_session_factory = None
_library_base_dir = None
_category_prefix = "_"  # Default prefix for category folders


def set_dependencies(
    session_factory: Callable,
    library_base_dir: Optional[str] = None,
    category_prefix: str = "_",
) -> None:
    """Set dependencies from main app"""
    global _session_factory, _library_base_dir, _category_prefix
    _session_factory = session_factory
    _category_prefix = category_prefix
    if library_base_dir:
        _library_base_dir = Path(library_base_dir)


def resolve_file_path(stored_path: str) -> Path:
    """
    Resolve a file path from the database to the actual filesystem location.

    This handles cases where:
    - Path is stored as absolute (e.g., from Docker container: /app/local/data/...)
    - Path needs to be resolved relative to configured library_dir

    Args:
        stored_path: File path stored in database (may be absolute or relative)

    Returns:
        Resolved Path object pointing to actual file location

    Raises:
        FileNotFoundError: If file cannot be found after resolution attempts
    """
    stored = Path(stored_path)

    # If stored path exists as-is, use it (same environment)
    if stored.exists():
        return stored

    # Try resolving relative to library_dir if configured
    if _library_base_dir:
        # Extract the relative path from stored path
        # This handles cases where stored path is from different environment
        # Example: /app/local/data/_Magazines/... -> _Magazines/...

        # Find the library folder marker (e.g., "_Magazines", "_Comics", etc.)
        parts = stored.parts
        # Build category markers from constants (e.g., "_Magazines", "_Comics")
        category_markers = [f"{_category_prefix}{category}" for category in CATEGORIES]

        for i, part in enumerate(parts):
            if part in category_markers:
                # Reconstruct path from category marker onwards
                relative_path = Path(*parts[i:])
                resolved = _library_base_dir / relative_path
                if resolved.exists():
                    logger.debug(f"Resolved path: {stored_path} -> {resolved}")
                    return resolved
                break

    # Last resort: check if it's directly under library_dir
    if _library_base_dir:
        filename = stored.name
        # Search recursively for the file (last resort, slower)
        for candidate in _library_base_dir.rglob(filename):
            if candidate.is_file():
                logger.warning(
                    f"Found file by name search: {stored_path} -> {candidate}"
                )
                return candidate

    # File not found after all attempts
    raise FileNotFoundError(
        f"File not found: {stored_path} (library_dir: {_library_base_dir})"
    )


def parse_month_string(month_str: Optional[str]) -> Tuple[int, str]:
    """
    Parse a month string, handling multi-month formats like "June/July".

    Args:
        month_str: Month string to parse (e.g., "June", "June/July", "Jan-Feb")

    Returns:
        Tuple of (month_number, normalized_month_string)
        month_number is 1-12 (defaults to 1 if unparseable)
    """
    if not month_str:
        return 1, ""

    month_str = month_str.strip()
    if not month_str:
        return 1, ""

    # Handle multi-month formats: "June/July", "Jan-Feb", "March / April"
    # Use the first month for the date, but preserve original string
    separators = ["/", "-", "&"]
    first_month = month_str

    for sep in separators:
        if sep in month_str:
            first_month = month_str.split(sep)[0].strip()
            break

    # Look up the month number
    month_num = MONTH_TO_NUMBER.get(first_month.lower(), 0)

    # If not found, default to 1
    if month_num == 0:
        month_num = 1

    return month_num, month_str


def get_periodical_or_404(db_session: Session, periodical_id: int):
    """
    Fetch a periodical by ID or raise 404 HTTPException.

    Args:
        db_session: Active database session
        periodical_id: ID of the periodical to fetch

    Returns:
        Periodical object

    Raises:
        HTTPException: 404 if periodical not found

    Usage:
        magazine = get_periodical_or_404(db, magazine_id)
    """
    magazine = (
        db_session.query(Periodical).filter(Periodical.id == periodical_id).first()
    )

    if not magazine:
        raise HTTPException(status_code=404, detail=ErrorMessages.MAGAZINE_NOT_FOUND)

    return magazine


def get_periodical_with_file(db_session: Session, periodical_id: int) -> Tuple:
    """
    Fetch a periodical by ID and resolve its file path.

    This combines the common pattern of fetching a periodical and resolving
    its file path with proper error handling.

    Args:
        db_session: Active database session
        periodical_id: ID of the periodical to fetch

    Returns:
        Tuple of (periodical, resolved_file_path)

    Raises:
        HTTPException: 404 if periodical or file not found

    Usage:
        magazine, file_path = get_periodical_with_file(db, magazine_id)
    """
    magazine = get_periodical_or_404(db_session, periodical_id)

    try:
        file_path = resolve_file_path(magazine.file_path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return magazine, file_path


def get_periodical_paths(
    db_session: Session, periodical_id: int
) -> Tuple[Path, Optional[Path]]:
    """
    Get file and cover paths for a periodical.

    Args:
        db_session: Active database session
        periodical_id: ID of the periodical

    Returns:
        Tuple of (file_path, cover_path) as Path objects
        cover_path is None if not set

    Raises:
        HTTPException: 404 if periodical not found

    Usage:
        file_path, cover_path = get_periodical_paths(db, magazine_id)
    """
    magazine = get_periodical_or_404(db_session, periodical_id)

    file_path = Path(magazine.file_path)
    cover_path = Path(magazine.cover_path) if magazine.cover_path else None

    return file_path, cover_path
