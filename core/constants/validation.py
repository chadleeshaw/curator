"""
Validation constants for periodical detection and filtering.

Used to distinguish periodicals from books, collections, and other non-periodical content.
"""

import re

from core.constants.category import (
    ACCEPTED_NEWSNAB_CATEGORIES,
    REJECTED_NEWSNAB_CATEGORIES,
)
from core.constants.date import get_month_year_patterns, get_season_regex_pattern, get_season_year_patterns
from core.constants.title import COLLECTION_SET_NUMBER_PATTERN

# ==============================================================================
# Newsnab Category Codes
# ==============================================================================

# Re-export from category constants for backwards compatibility
NEWSNAB_BOOK_CATEGORIES = REJECTED_NEWSNAB_CATEGORIES
"""Book categories to reject (not periodicals)"""

NEWSNAB_PERIODICAL_CATEGORIES = ACCEPTED_NEWSNAB_CATEGORIES
"""Periodical categories to accept"""


# ==============================================================================
# Periodical Indicator Patterns
# ==============================================================================

# Regex patterns that indicate content IS a periodical issue
# These patterns suggest recurring publication with dates/issue numbers
#
# Note: Date patterns are now generated dynamically to support multiple languages.
# Use get_periodical_patterns() to get the full list with multilingual support.
PERIODICAL_PATTERNS_STATIC = [
    # Issue/Number patterns - strong indicators
    r"\b(issue|no\.?|number|nr\.?)\s*\d+\b",
    r"#\d+\b",  # "#123"
    # Volume patterns - moderate indicators
    r"\b(vol\.?|volume)\s*\d+",
    r"\bv\d+\b",  # Bare volume shorthand: "v12", "v5" (common in comics and illustrated periodicals)
    # Bare issue number after title text (common in NZB titles without "Issue"/"No." prefix)
    # Matches: "Illustrated Comix 07", "Weekly Review 12", "Magazine 5"
    # Requires a letter before the space+number to avoid matching standalone numbers
    r"(?<=[a-z])\s+\d{1,3}\b",
    # Combined volume + issue - very strong indicator
    r"\bv\d+\s+(i|n|no\.?)\d+\b",  # "V12 N3", "V5 I2"
    # Weekly/bi-weekly date formats
    r"\b\d{4}[\.\s]\d{2}[\.\s]\d{2}\b",  # "2024.01.20" or "2024 01 20" (The Economist style)
    # Magazine/PDF collections - often contain multiple issues (valuable!)
    r"\bmagazines?\s+(collection|pack|bundle)\b",
    r"\b(collection|pack|bundle)\s+.{0,20}\bpdf\b",
    r"\b\d+\s+.{0,30}\bmagazines?\b.{0,20}\b(collection|pdf)\b",  # "60 ... Magazines Collection/PDF"
    # Full/Complete collection archives (e.g., from Internet Archive)
    r"\b(complete|full|entire)\s+(collection|run|archive)\b",
]
"""Static periodical patterns (non-date-based)"""


def get_periodical_patterns(languages: list[str] | None = None) -> list[str]:
    """
    Get complete list of periodical indicator patterns with multilingual date support.

    Args:
        languages: List of language names to include. If None, includes all supported languages.

    Returns:
        List of regex pattern strings for detecting periodical indicators

    Example:
        >>> patterns = get_periodical_patterns(["English", "Spanish"])
        >>> # Returns patterns matching dates in English and Spanish, plus all static patterns
    """
    patterns = list(PERIODICAL_PATTERNS_STATIC)
    patterns.extend(get_month_year_patterns(languages))
    patterns.extend(get_season_year_patterns(languages))
    return patterns


# For backwards compatibility - default to all languages
PERIODICAL_PATTERNS = get_periodical_patterns()


# ==============================================================================
# Compiled Collection & Season Detection Patterns
# ==============================================================================

_COLLECTION_KEYWORDS = ("collection", "pack", "bundle", "complete", "full", "entire")

COLLECTION_DETECTION_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in PERIODICAL_PATTERNS_STATIC if any(kw in p for kw in _COLLECTION_KEYWORDS)
]
"""Compiled regexes from PERIODICAL_PATTERNS_STATIC that identify collection/pack/bundle titles."""

COLLECTION_SET_NUMBER_COMPILED = re.compile(COLLECTION_SET_NUMBER_PATTERN, re.IGNORECASE)
"""Compiled version of COLLECTION_SET_NUMBER_PATTERN for direct use."""

SEASON_DETECTION_PATTERN = re.compile(rf"\b({get_season_regex_pattern()})\b", re.IGNORECASE)
"""Compiled multilingual season detection regex (e.g. Spring, Summer, primavera, hiver …)."""


# Patterns that indicate content is NOT a periodical (anti-patterns)
# These are checked FIRST to quickly filter out movies, TV shows, audiobooks, etc.
ANTI_PERIODICAL_PATTERNS = [
    # ============================================================================
    # Video Resolution & Quality Indicators (HIGHEST PRIORITY - most common)
    # ============================================================================
    # Resolution indicators
    r"\b(2160p|1440p|1080p|720p|576p|480p|360p)\b",
    r"\b(4k|8k|uhd|hd|sd|fhd|qhd)\b",
    # Video quality/source indicators
    r"\b(bluray|blu[\s\-]?ray|bdrip|brrip|bd[\-\s]?rip)\b",
    r"\b(dvdrip|dvd[\-\s]?rip|dvdscr|dvd9|dvd5)\b",
    r"\b(webrip|web[\-\s]?rip|webdl|web[\-\s]?dl|web\-dl)\b",
    r"\b(hdtv|pdtv|hdcam|hdcam[\-\s]?rip|hdts)\b",
    r"\b(cam[\-\s]?rip|telesync|ts|tc|telecine|ppv[\-\s]?rip|screener|scr)\b",
    # Note: PROPER/REPACK removed - also used in magazine scene releases
    # ============================================================================
    # Video Codecs & Containers
    # ============================================================================
    # Modern codecs
    r"\b(x264|x265|x\.264|x\.265)\b",
    r"\b(h264|h265|h\.264|h\.265)\b",
    r"\b(hevc|avc|vc[\-]?1)\b",
    r"\b(av1|vp9|vp8)\b",
    # Older/legacy codecs
    r"\b(xvid|divx|mpeg|mpeg2|mpeg4)\b",
    r"\b(wmv|wmv3|vc1)\b",
    # Container formats
    r"\b(matroska|mkv|remux)\b",
    # ============================================================================
    # Audio Codecs & Quality
    # ============================================================================
    r"\b(aac|ac3|dd5\.1|dd5|dts|dts[\-\s]?hd|dts[\-\s]?ma|truehd|atmos)\b",
    r"\b(flac|opus|vorbis|mp3|eac3|e[\-\s]?ac[\-\s]?3)\b",
    r"\b(5\.1|7\.1|2\.0|stereo|multi[\-\s]?audio|dual[\-\s]?audio)\b",
    # ============================================================================
    # Video File Extensions (when appearing in NZB titles)
    # ============================================================================
    r"\.(mp4|avi|mkv|mov|wmv|flv|m4v|mpg|mpeg|m2ts|ts|vob|iso|img)[\s\-\.\[]",
    # ============================================================================
    # TV Show Indicators
    # ============================================================================
    r"\btv[\s\-]?(show|series|episode|season)\b",
    r"\b(s\d{1,2}[\s\-\.]?e\d{1,2}|season[\s\-\.]\d+|episode[\s\-\.]\d+)\b",  # S01E01, Season 1
    r"\b\d{1,2}x\d{1,2}\b",  # 1x01 episode notation
    r"\b(complete[\s\-]?series|tv[\s\-]?pack|season[\s\-]?pack)\b",
    # ============================================================================
    # Movie/Film Indicators
    # ============================================================================
    r"\b(movie|film|cinema|theatrical)\b",
    r"\b(extended[\s\-]?cut|director[\s\-]?s[\s\-]?cut|unrated|uncut)\b",
    r"\b(imax|criterion|restored)\b",
    # ============================================================================
    # Documentary Indicators
    # ============================================================================
    r"\b(documentary|docu[\s\-]?series|docuseries)\b",
    # ============================================================================
    # Audiobook Indicators
    # ============================================================================
    r"\b(audiobook|audio[\s\-]?book|unabridged|abridged)\b",
    r"\b(narrated[\s\-]?by|narrator)\b",
    # ============================================================================
    # Music/Soundtrack Indicators
    # ============================================================================
    r"\b(soundtrack|ost|original[\s\-]?score|original[\s\-]?motion[\s\-]?picture)\b",
    r"\b(album|discography|live[\s\-]?concert)\b",
    # ============================================================================
    # Video Content Indicators (generic)
    # ============================================================================
    r"\bvideo\b",  # Generic video content indicator
    # ============================================================================
    # Release Group Tags (common in video releases)
    # ============================================================================
    r"\b(yify|rarbg|etrg|sparks|cmrg|fleet|ntb|shortbrehd)\b",
    r"\b(svengoolie)\b",  # TV show host (not a periodical)
    # ============================================================================
    # Multi-Subtitle/Language (common in video)
    # ============================================================================
    r"\b(multi[\-\s]?sub|multisub|multi[\-\s]?lang)\b",
    # ============================================================================
    # Book/Novel Series Indicators
    # ============================================================================
    r"\bbooks?\s+\d+\b",  # "Book 1", "Books 2" - novel series numbering
    # ============================================================================
    # Collection Range Indicators (packs, not single issues)
    # ============================================================================
    r"\b(volumes?|issues?|books?|parts?)\s+\d+\s*[-–]\s*\d+",  # "Volumes 1-5", "Issues 10-20"
]


# ==============================================================================
# File Size Heuristics (in MB)
# ==============================================================================

# Typical file size ranges for different periodical types
FILE_SIZE_MIN_MB = 5  # Smaller files likely articles/books
FILE_SIZE_MAX_MB = 1000  # Larger files likely collections/packs

# Detailed ranges by type (for future enhancement)
FILE_SIZE_RANGES = {
    "magazine_pdf": (10, 500),  # Typical magazine PDF
    "comic_cbz": (50, 500),  # Comic book archive
    "newspaper_pdf": (5, 100),  # Newspapers are often smaller
}


# ==============================================================================
# Quality and Release Group Indicators
# ==============================================================================

# These don't directly indicate periodical/non-periodical,
# but help with metadata extraction quality assessment
# Note: "True PDF" is a PREFERRED quality for periodicals - indicates the PDF contains
# both searchable text AND high-quality images (vs. image-only scans)
QUALITY_INDICATORS = [
    "true pdf",
    "true.pdf",
    "retail",
    "original",
    "hq",
    "high quality",
    "scan",
    "digital",
    "proper",  # Scene release terminology - used in both video and periodical releases
    "repack",  # Scene release terminology - used in both video and periodical releases
]

# Common release group patterns (for removal during parsing)
RELEASE_GROUP_PATTERNS = [
    r"-[A-Z0-9]+$",  # "-PHOTOFILEv2", "-MAGAZINES"
    r"\[[A-Z0-9]+\]$",  # "[PHOTOFILE]"
]
