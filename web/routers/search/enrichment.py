"""
Result enrichment with parsed metadata.

Parses search result titles on the backend using existing parsers so the
frontend doesn't need to duplicate title-parsing logic.  Each result gets
a ``parsed_title`` dict ready for direct consumption by the UI.
"""

import logging
from typing import Any, Dict, List

from core.constants.date import SEASON_CANONICAL_NAMES
from core.constants.validation import (
    COLLECTION_DETECTION_PATTERNS,
    COLLECTION_SET_NUMBER_COMPILED,
    SEASON_DETECTION_PATTERN,
)
from core.parsers.metadata import FilenameParser

logger = logging.getLogger(__name__)

# Module-level parser instance (stateless, safe to reuse)
_filename_parser = FilenameParser()


def _detect_collection(title: str) -> bool:
    """
    Check if a title represents a collection/pack/bundle.

    Uses patterns from ``PERIODICAL_PATTERNS_STATIC`` plus the set-number
    pattern (e.g. "Set #5", "Pack 3") which also implies a collection.

    Args:
        title: Raw or normalised title string

    Returns:
        True if the title matches known collection patterns
    """
    normalised = title.replace(".", " ").replace("_", " ")
    if any(p.search(normalised) for p in COLLECTION_DETECTION_PATTERNS):
        return True
    # "Set #5", "Pack 3", etc. also imply a collection
    if COLLECTION_SET_NUMBER_COMPILED.search(normalised):
        return True
    return False


def _extract_season(title: str) -> str | None:
    """
    Extract a season name from the title using the centralised multilingual pattern.

    Returns:
        Canonical season label (e.g. "Spring") or None
    """
    normalised = title.replace(".", " ").replace("_", " ")
    m = SEASON_DETECTION_PATTERN.search(normalised)
    if m:
        raw = m.group(1).lower()
        return SEASON_CANONICAL_NAMES.get(raw, raw.capitalize())
    return None


def _parse_single_result(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a ``parsed_title`` dict for one search result.

    Attempts NZB-style parsing first, then falls back to simple heuristics
    so *every* result gets at least a stub entry (is_collection, etc.).

    Returns:
        Dict with keys: year, month, issue, volume, season, is_collection
    """
    title = result.get("title", "")

    # Defaults
    year = 0
    month = 0
    issue = 0
    volume = 0
    season = None
    is_collection = _detect_collection(title)

    # Try full NZB parser (already exists on backend)
    nzb = _filename_parser.extract_from_nzb_title(title)
    if nzb:
        year = nzb.get("year") or 0
        month = nzb.get("month") or 0
        issue = nzb.get("issue") or 0
        volume = nzb.get("volume") or 0
        month_name = nzb.get("month_name")
        if month_name and month_name.lower() in SEASON_CANONICAL_NAMES:
            season = SEASON_CANONICAL_NAMES[month_name.lower()]
    else:
        # NZB parser returned None (anti-periodical patterns).
        # Result is already in the pipeline so it passed filter_non_periodicals.
        # Attempt minimal extraction from publication_date.
        pass

    # Season fallback: check title directly
    if not season:
        season = _extract_season(title)

    # If month still missing, try publication_date (but not for collections —
    # collections should group under year 0, not a random upload date)
    if not is_collection and month == 0 and result.get("publication_date"):
        pub = result["publication_date"]
        # publication_date can be ISO string or datetime
        if isinstance(pub, str):
            try:
                parts = pub.split("-")
                if len(parts) >= 2:
                    m = int(parts[1])
                    if 1 <= m <= 12:
                        month = m
                    if year == 0 and len(parts) >= 1:
                        y = int(parts[0])
                        if 1900 <= y <= 2100:
                            year = y
            except (ValueError, IndexError):
                pass

    # For collections, try to extract set number
    if is_collection and issue == 0:
        set_match = COLLECTION_SET_NUMBER_COMPILED.search(title.replace(".", " ").replace("_", " "))
        if set_match:
            issue = int(set_match.group(1))

    # Also enrich raw_metadata with volume/issue if available (backend → frontend bridge)
    raw_meta = result.get("raw_metadata") or result.get("metadata") or {}
    if volume and "volume" not in raw_meta:
        raw_meta["volume"] = volume
    if issue and "issue" not in raw_meta:
        raw_meta["issue"] = issue

    # Extract size and file count from raw_metadata (provided by Newsnab/IA)
    size = raw_meta.get("size", 0) or 0
    files = raw_meta.get("files", 0) or 0

    # Collections group under year 0 so the UI shows them under "📦 Collections"
    if is_collection:
        year = 0
        month = 0

    return {
        "year": year,
        "month": month,
        "issue": issue,
        "volume": volume,
        "season": season,
        "is_collection": is_collection,
        "size": size,
        "files": files,
    }


def enrich_results_with_parsed_metadata(results: List[Dict[str, Any]]) -> None:
    """
    Add ``parsed_title`` dict to every result **in place**.

    Called in the search pipeline so the frontend receives pre-parsed
    metadata and no longer needs to duplicate title-parsing logic.

    Args:
        results: List of result dicts (modified in place)
    """
    for result in results:
        result["parsed_title"] = _parse_single_result(result)

    parsed_count = sum(1 for r in results if r.get("parsed_title", {}).get("year", 0) > 0)
    logger.debug(
        f"Enriched {len(results)} results with parsed metadata "
        f"({parsed_count} with year, "
        f"{sum(1 for r in results if r.get('parsed_title', {}).get('is_collection'))} collections)"
    )
