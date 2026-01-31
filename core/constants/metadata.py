"""
Metadata aggregation constants and configuration defaults

IMPORTANT: Metadata is aggregated PER-FIELD, not per-source.
This means different fields can come from different sources:
- Year from OCR (confident)
- Issue number from filename (OCR didn't detect it)
- Month from text_scan
- Result: Combined metadata from multiple sources ✅

Each field independently selects the best source based on:
1. Priority order (ocr > text_scan > filename)
2. Confidence threshold (must meet minimum)
3. Availability (source has non-null value)

TYPICAL METADATA BY SOURCE:
- OCR/text_scan: Usually only year + month (from cover)
- Filename: Can have year, month, issue_number, volume, special_edition
- Best practice: Let OCR/text_scan provide year+month, filename provides rest
"""

# ==============================================================================
# Metadata Source Priority
# ==============================================================================

DEFAULT_METADATA_SOURCE_PRIORITY = ["ocr", "text_scan", "filename"]
"""
Default priority order for metadata sources (first = highest priority).

Available sources:
- ocr: Image-based OCR text extraction
- text_scan: Direct PDF/EPUB text extraction
- filename: Filename parsing

Default: OCR first (most accurate for scanned magazines), then text_scan, then filename
"""

# ==============================================================================
# Confidence Thresholds
# ==============================================================================

DEFAULT_METADATA_CONFIDENCE_THRESHOLDS = {
    "ocr": 70,  # OCR must be 70%+ confident to be used
    "text_scan": 50,  # Text scan usually high quality, lower threshold OK
    "filename": 0,  # Always accept filename parsing (no confidence score)
}
"""
Minimum confidence thresholds (0-100) for each metadata source.

Source must meet or exceed threshold to be used.
If below threshold, next source in priority order is tried.
"""

# ==============================================================================
# Per-Field Confidence Overrides
# ==============================================================================

DEFAULT_FIELD_CONFIDENCE_OVERRIDES = {
    "year": {
        "ocr": 80,  # Years are critical - require higher OCR confidence
    },
    "month": {
        "ocr": 60,  # Month names are easier to OCR - lower threshold OK
    },
    "issue_number": {
        "ocr": 75,  # Issue numbers moderately important (rare in OCR/text_scan)
    },
    "volume": {
        "ocr": 75,  # Volume numbers moderately important (rare in OCR/text_scan)
    },
}
"""
Per-field confidence threshold overrides.

Allows fine-tuning thresholds for specific metadata fields.
Format: {field_name: {source_name: threshold}}

NOTE: OCR/text_scan typically only extract year and month from covers.
Issue numbers, volumes, and special editions are less common in OCR output.
"""

# ==============================================================================
# Metadata Field Configuration
# ==============================================================================

METADATA_FIELDS = ["year", "month", "volume", "issue_number", "special_edition"]
"""
List of metadata fields that can be aggregated from multiple sources.
"""

CONFIDENCE_FIELDS = [
    "year_confidence",
    "month_confidence",
    "volume_confidence",
    "issue_number_confidence",
]
"""
List of confidence score field names corresponding to METADATA_FIELDS.
"""
