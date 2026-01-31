"""
Metadata builder utilities for constructing parsed_metadata, derived_metadata, and extra_metadata.
"""

from datetime import datetime
from typing import Dict, Any, Optional
from core.parsers.models import ParsedMetadata


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

    return file_scan


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
    - text_scan: year, month, issue_number, volume, special_edition
    - ocr_scan: year, month, issue_number, volume, special_edition

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

    # Fields to merge
    fields = [
        "title",  # Title from any source
        "year",
        "month",
        "month_name",
        "issue_number",
        "volume",
        "country",
        "language",
        "special_edition",
        "is_special_edition",
        "special_edition_name",
    ]

    derived = {}

    for field in fields:
        # Try each source in priority order
        for source_name in source_priority:
            source_data = sources.get(source_name, {})
            value = source_data.get(field)

            if value is None:
                continue

            # Get confidence
            confidence = source_data.get("confidence", 0.0)

            # Convert string confidence to float
            if isinstance(confidence, str):
                confidence_map = {"high": 0.85, "medium": 0.60, "low": 0.30}
                confidence = confidence_map.get(confidence, 0.0)

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
        if month_value and isinstance(month_value, int):
            month = month_value

    # Create datetime
    try:
        if month and 1 <= month <= 12:
            return datetime(year, month, 1)
        else:
            # Only year available - default to January
            return datetime(year, 1, 1)
    except (ValueError, OverflowError):
        # Invalid date values
        return None
