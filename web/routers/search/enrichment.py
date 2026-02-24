"""
Result enrichment with parsed metadata.

Parses search result titles on the backend using existing parsers so the
frontend doesn't need to duplicate title-parsing logic.  Each result gets
a ``parsed_title`` dict ready for direct consumption by the UI.
"""

import logging
import re
from typing import Any, Dict, List

from core.constants.date import MONTHS_BY_LANGUAGE, SEASON_CANONICAL_NAMES
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


# Flat map of every multilingual month name (full only) → month number (1–12).
# Built once at import time from the centralised MONTHS_BY_LANGUAGE constant.
_MULTILINGUAL_MONTH_NAME_TO_NUM: dict[str, int] = {
    name.lower(): i for lang_data in MONTHS_BY_LANGUAGE.values() for i, name in enumerate(lang_data.get("full", []), 1)
}

# Regex that matches any known multilingual month name as a whole word.
_MULTILINGUAL_MONTH_RE = re.compile(
    r"\b(" + "|".join(re.escape(n) for n in sorted(_MULTILINGUAL_MONTH_NAME_TO_NUM, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


def _extract_multilingual_month(title: str) -> int:
    """
    Scan *title* for any multilingual month name and return its month number (1–12).

    Returns 0 if no month name is found.
    """
    m = _MULTILINGUAL_MONTH_RE.search(title)
    if m:
        return _MULTILINGUAL_MONTH_NAME_TO_NUM.get(m.group(1).lower(), 0)
    return 0


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
        # The NZB parser defaults month=1 (January) when only a year is present and
        # no month name was actually found in the title.  Treat that as no month.
        month_name = nzb.get("month_name")
        raw_month = nzb.get("month") or 0
        month = raw_month if (raw_month != 1 or month_name) else 0
        issue = nzb.get("issue") or 0
        volume = nzb.get("volume") or 0
        if month_name and month_name.lower() in SEASON_CANONICAL_NAMES:
            season = SEASON_CANONICAL_NAMES[month_name.lower()]
    else:
        # NZB parser returned None (anti-periodical patterns).
        # Result is already in the pipeline so it passed filter_non_periodicals.
        # Remaining fallbacks below will attempt minimal extraction.
        pass
    # Season fallback: check title directly
    if not season:
        season = _extract_season(title)

    # Multilingual month fallback: the NZB parser only recognises English month names.
    # If month is still 0, scan the title for any known multilingual month name.
    if month == 0:
        month = _extract_multilingual_month(title)

    # Vol+No fallback: the NZB parser sometimes misidentifies "No." as a country code
    # (e.g. "No. 6" → country=NO) and drops the issue number.  When volume was found
    # but issue was not, re-scan the title for an explicit "No." or "No" pattern.
    if not is_collection and volume > 0 and issue == 0:
        no_match = re.search(r"\bNo\.?\s*(\d+)", title, re.IGNORECASE)
        if no_match:
            issue = int(no_match.group(1))

    # Issue+Month+2-digit-year fallback: handles IA titles like "National Geographic 1888 10 01"
    # where the NZB parser fails entirely (confidence=low).  Pattern: <issue> <MM> <YY> at the
    # end of the title — three standalone numbers where the second is a valid month (1–12) and
    # the third is exactly 2 digits (two-digit year, 00–99).
    # 2-digit year: 00–29 → 2000–2029, 30–99 → 1930–1999.
    if not is_collection and year == 0 and month == 0 and issue == 0 and volume == 0:
        two_digit_year_match = re.search(r"(?<!\d)(\d+)\s+(\d{1,2})\s+(\d{2})(?!\d)\s*$", title)
        if two_digit_year_match:
            candidate_issue = int(two_digit_year_match.group(1))
            candidate_month = int(two_digit_year_match.group(2))
            candidate_yy = int(two_digit_year_match.group(3))
            if 1 <= candidate_month <= 12:
                issue = candidate_issue
                month = candidate_month
                year = 2000 + candidate_yy if candidate_yy <= 29 else 1900 + candidate_yy
                # NOTE: the 29/30 cutoff follows the ISO 8601 two-digit year windowing
                # convention.  Revisit after 2029 when "30" starts meaning 2030.

    # Bare-number fallback: when no issue/volume was extracted, scan the title for a
    # standalone number that isn't the year.  This covers two cases:
    #   1. Fully unparseable titles ("Wired 7 in US") — year=0 as well
    #   2. Partially-parsed titles where the year was found but issue/volume were not
    #      ("Historia National Geographic 013 2005") — prevents all issues from the same
    #      year collapsing into one dedup key.
    # Run BEFORE the publication_date backfill so that titles like
    # "DOSSIERES 10" (issue found here) suppress the spurious upload-date month.
    if not is_collection and issue == 0 and volume == 0:
        # Search for every standalone number in the title; pick the first one that
        # is not a plausible year (1900–2100) and not the already-extracted year.
        for m in re.finditer(r"(?<!\d)(\d{1,4})(?!\d)", title):
            candidate = int(m.group(1))
            if not (1900 <= candidate <= 2100) and candidate != year:
                issue = candidate
                break

    # If month still missing, try publication_date (but not for collections —
    # collections should group under year 0, not a random upload date; and not
    # when issue/volume was already found — those are volume-numbered series
    # where publication_date is just an upload date, not an issue month)
    if not is_collection and month == 0 and issue == 0 and volume == 0 and result.get("publication_date"):
        pub = result["publication_date"]
        # publication_date can be ISO string or datetime
        if isinstance(pub, str):
            try:
                parts = pub.split("-")
                if len(parts) >= 2:
                    month_num = int(parts[1])
                    if 1 <= month_num <= 12:
                        month = month_num
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
