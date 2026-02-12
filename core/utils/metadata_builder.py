"""
Metadata builder utilities for constructing parsed_metadata, derived_metadata, and extra_metadata.
"""

import logging
from datetime import UTC, datetime
from typing import Dict, Any, Optional
from core.constants.ocr import OCR_MAX_VOLUME
from core.parsers.models import ParsedMetadata

logger = logging.getLogger(__name__)


def build_file_scan(parsed: ParsedMetadata) -> Dict[str, Any]:
    """
    Build file_scan structure from parsed file metadata.

    Args:
        parsed: ParsedMetadata from parser

    Returns:
        Dictionary with file_scan structure
    """
    file_scan = {
        "parse_source": parsed.parse_source or "file",
        "confidence": parsed.confidence,
    }

    # Add all extracted fields
    if parsed.year:
        file_scan["year"] = parsed.year
    if parsed.month:
        file_scan["month"] = parsed.month
    if parsed.month_name:
        file_scan["month_name"] = parsed.month_name
    if parsed.issue_number:
        file_scan["issue_number"] = parsed.issue_number
    if parsed.volume:
        file_scan["volume"] = parsed.volume
    if parsed.country:
        file_scan["country"] = parsed.country
    if parsed.language:
        file_scan["language"] = parsed.language
    if parsed.is_special_edition:
        file_scan["is_special_edition"] = parsed.is_special_edition
    if parsed.special_edition_name:
        file_scan["special_edition_name"] = parsed.special_edition_name
    if parsed.title:
        file_scan["title"] = parsed.title
    if parsed.base_title:
        file_scan["base_title"] = parsed.base_title
    if parsed.original_filename:
        file_scan["filename"] = parsed.original_filename
    if parsed.file_path:
        file_scan["full_path"] = str(parsed.file_path)
    if parsed.matched_pattern:
        file_scan["matched_pattern"] = parsed.matched_pattern

    # Timestamp ID pattern extracts the import timestamp, not the publication date.
    # Set per-field low confidence for date fields so OCR/text scan can override them.
    if parsed.matched_pattern == "timestamp_id":
        for date_field in ("year", "month", "month_name"):
            if date_field in file_scan:
                file_scan[f"{date_field}_confidence"] = 0.10

    return file_scan


def _normalize_month_to_int(month_value: Any) -> Optional[int]:
    """
    Normalize a month value to an integer (1-12).

    Handles:
    - Integer month numbers (pass through)
    - String month names ("January", "jan", etc.) via MONTH_TO_NUMBER

    Args:
        month_value: Month as int or string name

    Returns:
        Integer month (1-12) or None if not recognized
    """
    if isinstance(month_value, int):
        return month_value if 1 <= month_value <= 12 else None

    if isinstance(month_value, str):
        from core.constants.date import MONTH_TO_NUMBER

        month_int = MONTH_TO_NUMBER.get(month_value.lower())
        if month_int:
            return month_int

    return None


def build_derived_metadata(
    file_scan: Optional[Dict[str, Any]] = None,
    text_scan: Optional[Dict[str, Any]] = None,
    ocr_scan: Optional[Dict[str, Any]] = None,
    source_priority: Optional[list[str]] = None,
    confidence_thresholds: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """
    Build derived_metadata by merging scan sources with priority and confidence thresholds.

    Each field in derived_metadata includes:
    - value: The actual field value
    - source: Which scan provided this value (file_scan, text_scan, or ocr_scan)
    - confidence: Confidence score from that source

    Fields available from each source:
    - file_scan: title, year, month, month_name, issue_number, volume, country, language, is_special_edition, special_edition_name
    - text_scan: year, month, issue_number, volume, special_edition (aliased to is_special_edition)
    - ocr_scan: year, month, issue_number, volume, special_edition (aliased to is_special_edition)

    Note: Title only comes from filename parsing (file_scan). OCR/text scans don't extract titles.
    Note: issue_date is NOT in derived_metadata - it's calculated separately in the Periodical model
          from year/month when available, or left as volume/issue-only for periodicals without dates.

    Args:
        file_scan: File scan results from filename parsing
        text_scan: Text scan results from embedded PDF/EPUB text
        ocr_scan: OCR scan results from cover image analysis
        source_priority: Priority order (default: ["ocr_scan", "text_scan", "file_scan"])
        confidence_thresholds: Min confidence by source (default: {"ocr_scan": 0.70, "text_scan": 0.50, "file_scan": 0.0})

    Returns:
        Dictionary with derived metadata fields, each containing {value, source, confidence}

    Example:
        {
            "title": {"value": "National Geographic", "source": "file_scan", "confidence": 0.85},
            "year": {"value": 2024, "source": "ocr_scan", "confidence": 0.92},
            "month": {"value": 1, "source": "text_scan", "confidence": 0.75},
            "issue_number": {"value": "123", "source": "file_scan", "confidence": 0.85},
        }
    """
    if source_priority is None:
        source_priority = ["ocr_scan", "text_scan", "file_scan"]

    if confidence_thresholds is None:
        confidence_thresholds = {
            "ocr_scan": 0.70,
            "text_scan": 0.50,
            "file_scan": 0.0,
        }

    # Gather all sources
    sources = {
        "file_scan": file_scan or {},
        "text_scan": text_scan or {},
        "ocr_scan": ocr_scan or {},
    }

    # Fields to merge — each entry is the canonical field name.
    # Alias mappings below allow different scan sources to use different field names
    # for the same concept (e.g., file_scan uses "is_special_edition" while OCR uses "special_edition").
    fields = [
        "title",  # Title from any source
        "year",
        "month",
        "month_name",
        "issue_number",
        "volume",
        "country",
        "language",
        "is_special_edition",
        "special_edition_name",
    ]

    # Alias mappings: canonical field → list of alternate field names to check in sources.
    # This allows OCR's "special_edition" (bool) to compete with file_scan's "is_special_edition" (bool)
    # for the same derived field, so higher-priority sources can override lower-priority ones.
    field_aliases = {
        "is_special_edition": ["special_edition"],
    }

    derived = {}

    for field in fields:
        # Build the list of source field names to check for this canonical field
        source_field_names = [field] + field_aliases.get(field, [])

        # Try each source in priority order
        for source_name in source_priority:
            source_data = sources.get(source_name, {})

            # Check the canonical field name and any aliases
            value = None
            matched_field_name = field
            for fname in source_field_names:
                value = source_data.get(fname)
                if value is not None:
                    matched_field_name = fname
                    break

            if value is None:
                continue

            # Normalize month values to int so derived_metadata is always consistent
            if field == "month" and isinstance(value, str):
                value = _normalize_month_to_int(value)
                if value is None:
                    continue

            # Validate volume values - reject unreasonable numbers (zip codes, addresses, etc.)
            if field == "volume" and isinstance(value, (int, float)):
                if int(value) > OCR_MAX_VOLUME:
                    logger.debug(f"Rejecting unreasonable volume {value} from {source_name} (exceeds {OCR_MAX_VOLUME})")
                    continue

            # Get confidence - check per-field confidence first (e.g., year_confidence),
            # then overall_confidence, then generic confidence key.
            # OCR/text scans use "{field}_confidence" and "overall_confidence" (0-100 int scale),
            # while file_scan uses "confidence" (string like "high" or float 0-1).
            # Use matched_field_name for per-field keys (handles aliases like "special_edition_confidence").
            field_confidence_key = f"{matched_field_name}_confidence"
            confidence = source_data.get(field_confidence_key)
            if confidence is None:
                confidence = source_data.get("overall_confidence")
            if confidence is None:
                confidence = source_data.get("confidence", 0.0)

            # Convert string confidence to float (file_scan uses "high"/"medium"/"low")
            if isinstance(confidence, str):
                confidence_map = {"high": 0.85, "medium": 0.60, "low": 0.30}
                confidence = confidence_map.get(confidence, 0.0)

            # Normalize 0-100 scale to 0-1 (OCR/text scans use Tesseract's 0-100 scale)
            if isinstance(confidence, (int, float)) and confidence > 1.0:
                confidence = confidence / 100.0

            # Check if confidence meets threshold
            threshold = confidence_thresholds.get(source_name, 0.0)
            if confidence >= threshold:
                # This source wins for this field
                derived[field] = {
                    "value": value,
                    "source": source_name,
                    "confidence": confidence,
                }
                break

    # Ensure month_name is always consistent with the winning month value.
    # month and month_name can be won by different sources (e.g., month=5 from OCR,
    # month_name="February" from file_scan), so always derive month_name from the
    # winning month int to prevent mismatches.
    if "month" in derived:
        from core.constants.date import NUMBER_TO_MONTH

        month_int = derived["month"]["value"]
        month_name = NUMBER_TO_MONTH.get(month_int)
        if month_name:
            derived["month_name"] = {
                "value": month_name,
                "source": derived["month"]["source"],
                "confidence": derived["month"]["confidence"],
            }

    # Add merge configuration
    derived["_merge_config"] = {
        "source_priority": source_priority,
        "confidence_thresholds": confidence_thresholds,
    }

    return derived


def build_parsed_metadata(
    file_scan: Optional[Dict[str, Any]] = None,
    text_scan: Optional[Dict[str, Any]] = None,
    ocr_scan: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Build parsed_metadata structure with all scan results.

    Args:
        file_scan: File scan results
        text_scan: Text scan results
        ocr_scan: OCR scan results

    Returns:
        Dictionary with all scan results
    """
    parsed = {}

    if file_scan:
        parsed["file_scan"] = file_scan
    if text_scan:
        parsed["text_scan"] = text_scan
    if ocr_scan:
        parsed["ocr_scan"] = ocr_scan

    return parsed


def build_extra_metadata(
    imported_from: str,
    import_date: str,
    category: Optional[str] = None,
    import_method: str = "auto",
) -> Dict[str, Any]:
    """
    Build extra_metadata with import/provenance information only.

    Args:
        imported_from: Original filename
        import_date: ISO format import timestamp
        category: Content category
        import_method: "auto" or "manual"

    Returns:
        Dictionary with import metadata
    """
    extra = {
        "imported_from": imported_from,
        "import_date": import_date,
        "import_method": import_method,
    }

    if category:
        extra["category"] = category

    return extra


def sync_issue_date_from_derived(
    derived_metadata: Optional[Dict[str, Any]],
) -> Optional[datetime]:
    """
    Calculate issue_date from derived_metadata.

    This keeps the issue_date column in sync with the best available date data
    from all scan sources (file_scan, text_scan, ocr_scan).

    Args:
        derived_metadata: Derived metadata with year/month from best source

    Returns:
        datetime object for issue_date, or None if no date info available

    Logic:
        - If year + month available: datetime(year, month, 1)
        - If only year available: datetime(year, 1, 1)
        - If no year: None (periodical uses volume/issue for identification)

    Example:
        >>> derived = {
        ...     "year": {"value": 2024, "source": "ocr_scan", "confidence": 0.92},
        ...     "month": {"value": 3, "source": "text_scan", "confidence": 0.75}
        ... }
        >>> sync_issue_date_from_derived(derived)
        datetime(2024, 3, 1)
    """
    if not derived_metadata:
        return None

    # Extract year from derived metadata
    year_data = derived_metadata.get("year")
    if not year_data:
        return None

    year = year_data.get("value")
    if not year or not isinstance(year, int):
        return None

    # Extract month from derived metadata
    month_data = derived_metadata.get("month")
    month = None

    if month_data:
        month_value = month_data.get("value")
        if month_value is not None:
            if isinstance(month_value, int):
                month = month_value
            elif isinstance(month_value, str):
                # Handle string month names (e.g., "January") from OCR/text scans
                month = _normalize_month_to_int(month_value)
                if month:
                    logger.debug(f"Converted string month '{month_value}' to {month} in sync_issue_date")

    # Create datetime
    try:
        if month and 1 <= month <= 12:
            return datetime(year, month, 1, tzinfo=UTC)
        else:
            # Only year available - default to January
            return datetime(year, 1, 1, tzinfo=UTC)
    except (ValueError, OverflowError):
        # Invalid date values
        return None


def get_derived_field(periodical, field: str, fallback_extra: bool = True) -> Any:
    """
    Get a field value from derived_metadata, with fallback to extra_metadata.

    derived_metadata stores fields as {"value": ..., "source": ..., "confidence": ...}.
    extra_metadata stores fields as direct values (legacy).

    Args:
        periodical: Periodical database object
        field: Field name (e.g., "volume", "issue_number", "language")
        fallback_extra: Whether to fall back to extra_metadata (default: True)

    Returns:
        The field value, or None if not found
    """
    # Primary: derived_metadata
    derived = periodical.derived_metadata or {}
    if field in derived:
        entry = derived[field]
        if isinstance(entry, dict):
            return entry.get("value")
        return entry

    # Fallback: extra_metadata (legacy location)
    if fallback_extra:
        extra = periodical.extra_metadata or {}
        return extra.get(field)

    return None


def is_periodical_special_edition(periodical) -> bool:
    """
    Check if a periodical is a special edition using all metadata sources.

    Checks in order:
    1. derived_metadata.is_special_edition (unified field from all scan sources)
    2. extra_metadata.special_edition (legacy)
    3. Title pattern matching via is_special_edition()

    Args:
        periodical: Periodical database object

    Returns:
        True if the periodical is a special edition
    """
    from core.utils.general import is_special_edition

    # Check derived_metadata first (unified field: "is_special_edition")
    derived = periodical.derived_metadata or {}
    entry = derived.get("is_special_edition")
    if entry is not None:
        value = entry.get("value") if isinstance(entry, dict) else entry
        if value:
            return True

    # Check extra_metadata (legacy)
    extra = periodical.extra_metadata or {}
    if isinstance(extra, dict) and extra.get("special_edition") is not None:
        return True

    # Before title fallback, check if any scan explicitly determined NOT special edition.
    # If a scan returned special_edition=false, trust the scan over keyword matching.
    parsed = periodical.parsed_metadata or {}
    if isinstance(parsed, dict):
        for scan_key in ("ocr_scan", "text_scan", "file_scan"):
            scan = parsed.get(scan_key)
            if isinstance(scan, dict):
                for field_name in ("special_edition", "is_special_edition"):
                    val = scan.get(field_name)
                    if val is not None:
                        # Scan explicitly checked — return its verdict
                        return bool(val)

    # Fallback to title pattern matching (only if no scan addressed the field)
    if periodical.title and is_special_edition(periodical.title):
        return True

    return False
