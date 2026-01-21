"""
Regex patterns for parsing metadata from filenames and text.

This module consolidates all regex patterns used across the codebase.
Patterns are organized by category for easy maintenance and reuse.
"""

import re

# ==============================================================================
# DATE PATTERNS
# ==============================================================================

# ISO date formats
DATE_PATTERN_ISO_FULL = r"(\d{4})[-.\s](\d{1,2})[-.\s](\d{1,2})\b"
"""Pattern for full ISO dates: 2024-01-20, 2024.01.20, 2024 01 20"""

DATE_PATTERN_ISO_MONTH = r"(\d{4})[-.](\d{1,2})(?![-.\d])"
"""Pattern for ISO year-month: 2024-01, 2024.01"""

DATE_PATTERN_MONTH_YEAR_NUMERIC = r"\b(\d{1,2})[-/](\d{4})\b"
"""Pattern for numeric month-year: 01-2024, 1/2024"""

DATE_PATTERN_YEAR_ONLY = r"\b(\d{4})\b"
"""Pattern for standalone year: 2024"""

# Month name patterns (English)
DATE_PATTERN_FULL_MONTH_YEAR = (
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)[\s]+(\d{4})\b"
)
"""Pattern for full month name with year: January 2024"""

DATE_PATTERN_ABBR_MONTH_YEAR = r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?[\s]*(\d{4})\b"
"""Pattern for abbreviated month with year: Jan 2024, Jan2024"""

DATE_PATTERN_ABBR_MONTH_YEAR_NO_BOUNDARY = r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?(\d{4})"
"""Pattern for abbreviated month with year (no word boundaries): Jan2024 in middle of string"""

# Multi-month patterns
DATE_PATTERN_MULTI_MONTH = r"(.+?)\s*[-–]?\s*([A-Za-z]+)[/\-&]([A-Za-z]+)\s*(\d{4})"
"""Pattern for multi-month periods: June/July 2024, Jun/Jul2024"""

# ==============================================================================
# NZB METADATA PATTERNS
# ==============================================================================

# Country/Region patterns (most specific first)
NZB_COUNTRY_PATTERNS = [
    r"\b(USA?|UK|CA|AU|NZ|DE|FR|ES|IT|NL|SE|NO|DK|FI|JP|KR|CN|BR|MX|AR|IN)\b",
    r"\b(United\s+States|United\s+Kingdom|Europe|Asia|North\s+America)\b",
]
"""Patterns for detecting country/region indicators in NZB filenames"""

# Language patterns
NZB_LANGUAGE_PATTERNS = [
    r"\b(English|German|French|Spanish|Italian|Portuguese|Russian|Japanese|Korean|Chinese)\b",
]
"""Patterns for detecting language indicators in NZB filenames"""

# Edition/Variant patterns
NZB_EDITION_PATTERNS = [
    r"\b(International|Global|European|Asian|Special|Limited|Digital|Print)\s+(?:Edition|Ed\.?)\b",
    r"\b(?:Edition|Ed\.?)[\s._-]*(International|Global|European|Asian|Special|Limited)\b",
]
"""Patterns for detecting edition/variant indicators in NZB filenames"""

# Quality indicators
NZB_QUALITY_PATTERNS = [
    r"\b(True\.?PDF|HQ|High\.?Quality|Retail|Original)\b",
]
"""Patterns for detecting quality indicators in NZB filenames"""

# Release group patterns (at end of filename)
NZB_RELEASE_GROUP_PATTERNS = [
    r"-([A-Z][A-Z0-9]*v?\d*)$",  # -PHOTOFILEv2, -HQ, -RETAIL (must start with letter)
    r"\[([A-Z0-9]+)\]$",  # [PHOTOFILE]
]
"""Patterns for detecting release groups in NZB filenames"""

# Volume patterns
NZB_VOLUME_PATTERN = r"(?:vol\.?|volume|v)[\s]*(\d+)\b"
"""Pattern for volume numbers: Vol.12, Volume 5, V202"""

# Issue patterns
NZB_ISSUE_PATTERN = r"(?:issue|no\.?|number|nr\.?|n)[\s]*(\d+)\b|#(\d+)"
"""Pattern for issue numbers: Issue 389, No. 25, N25, #45"""

# ==============================================================================
# TITLE PATTERNS
# ==============================================================================

# Filename patterns
TITLE_PATTERN_DASH_MONTH_YEAR = r"(.+?)\s*-\s*([A-Za-z]{3,9})(\d{4})"
"""Pattern for Title - MonthYear: National Geographic - Dec2024"""

TITLE_PATTERN_DASH_MONTH_DOT_YEAR = r"(.+?)\s*-\s*([A-Za-z]{3,9})[\.\s]+(\d{4})"
"""Pattern for Title - Month.Year: Esquire.Africa-August.2023"""

TITLE_PATTERN_DOT_SEPARATED = r"^([^.]+)\.(January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.(\d{4})"
"""Pattern for Title.Month.Year: Wired.January.2024"""

TITLE_PATTERN_SPACE_MONTH_YEAR = r"(.+?)\s+([A-Za-z]+)\s+(\d{4})"
"""Pattern for Title Month Year: Wired January 2024"""

TITLE_PATTERN_SPACE_MONTH_ONLY = r"(.+?)\s+([A-Za-z]+)$"
"""Pattern for Title Month (no year): Wired January"""

TITLE_PATTERN_ISO_DATE = r"(.+?)\s+(\d{4})-(\d{2})$"
"""Pattern for Title YYYY-MM: PC Gamer 2024-12"""

TITLE_PATTERN_ISSUE_NUMBER = r"^(.+?)[\.\s]+(?:no\.?|number|issue)[\.\s]*(\d{1,3})[\.\s]+(\d{4})(?:[\.\s]+(.+))?$"
"""Pattern for Title No.XXX YYYY: PC Gamer No.405 2024"""

TITLE_PATTERN_VOLUME_ISSUE = (
    r"^(.+?)[\.\s]+vol\.?[\.\s]*(\d{1,3})[\.\s]+no\.?[\.\s]*(\d{1,3})[\.\s]+(?:.+?[\.\s]+)?(\d{4})"
)
"""Pattern for Title Vol.XX No.YY YYYY: 2600.Magazine.Vol.41.No.1.2024"""

TITLE_PATTERN_SEASONAL = r"^(.+?)[\.\s]+(spring|summer|fall|autumn|winter)[\.\s]+(\d{4})(?:[\.\s]+(.+))?$"
"""Pattern for Title Season YYYY: 2600 Winter 2024"""

TITLE_PATTERN_DATE_ONLY_COMPACT = r"^([A-Za-z]+)(\d{4})$"
"""Pattern for date-only filename (compact): Apr2001"""

TITLE_PATTERN_DATE_ONLY_SPACED = r"^([A-Za-z]+)\s+(\d{4})$"
"""Pattern for date-only filename (spaced): April 2001"""

# Cleaning patterns
TITLE_CLEANUP_BRACKETS = r"\[.*?\]|\(.*?\)"
"""Pattern to remove bracketed content from titles"""

TITLE_CLEANUP_LANGUAGE_CODES = r"[\s]+(?:de|en|fr|es|it|pt|ru|nl|pl|sv|no|fi|da|ja|ko|zh|ar)(?:[\s]|$)"
"""Pattern to remove language codes from titles (but not country codes like UK)"""

TITLE_CLEANUP_DESCRIPTORS = r"\b(?:quarterly|monthly|weekly|magazine|the|hacker|hybrid|digital|print)\b"
"""Pattern to remove common descriptor words from titles"""

TITLE_CLEANUP_TRAILING_DASH = r"\s*-\s*$"
"""Pattern to remove trailing dashes from titles"""

TITLE_CLEANUP_TRAILING_DASH_DIGITS = r"-\d{1,2}$"
"""Pattern to remove trailing dash+digits from titles: -01"""

TITLE_CLEANUP_TRAILING_SPACE_DIGITS = r"\s+\d{1,2}$"
"""Pattern to remove trailing space+digits from titles: ' 01'"""

# ==============================================================================
# PERIODICAL DETECTION PATTERNS
# ==============================================================================

# Issue/Number patterns - strong indicators
PERIODICAL_PATTERN_ISSUE_NUMBER = r"\b(issue|no\.?|number|nr\.?)\s*\d+\b"
"""Pattern for issue number indicators"""

PERIODICAL_PATTERN_HASH_NUMBER = r"#\d+\b"
"""Pattern for hash-style issue numbers: #123"""

# Volume patterns - moderate indicators
PERIODICAL_PATTERN_VOLUME = r"\b(vol\.?|volume)\s*\d+"
"""Pattern for volume indicators"""

# Combined volume + issue - very strong indicator
PERIODICAL_PATTERN_VOLUME_ISSUE_COMBINED = r"\bv\d+\s+(i|n|no\.?)\d+\b"
"""Pattern for combined volume+issue: V12 N3, V5 I2"""

# Weekly/bi-weekly date formats
PERIODICAL_PATTERN_WEEKLY_DATE = r"\b\d{4}[\.\s]\d{2}[\.\s]\d{2}\b"
"""Pattern for weekly date formats: 2024.01.20, 2024 01 20 (The Economist style)"""

# ==============================================================================
# ANTI-PERIODICAL PATTERNS (Book/Collection Indicators)
# ==============================================================================

ANTI_PERIODICAL_PATTERN_COMPLETE_COLLECTION = r"\b(complete|full|entire)\s+(collection|series)\b"
"""Pattern for complete collection indicators"""

ANTI_PERIODICAL_PATTERN_ANTHOLOGY = r"\banthology\b"
"""Pattern for anthology indicators"""

ANTI_PERIODICAL_PATTERN_OMNIBUS = r"\bomnibus\b"
"""Pattern for omnibus indicators"""

ANTI_PERIODICAL_PATTERN_COMPENDIUM = r"\bcompendium\b"
"""Pattern for compendium indicators"""

ANTI_PERIODICAL_PATTERN_COLLECTED_WORKS = r"\bcollected\s+(works|edition)\b"
"""Pattern for collected works indicators"""

ANTI_PERIODICAL_PATTERN_RANGE_VOLUMES = r"\b(volumes?|issues?)\s+\d+\s*-\s*\d+\b"
"""Pattern for volume/issue ranges: Volumes 1-5, Issues 10-20"""

ANTI_PERIODICAL_PATTERN_RANGE_SHORT = r"\b(vol|issue|no)\.?\s*\d+\s*-\s*\d+\b"
"""Pattern for abbreviated ranges: Vol 1-3, No 5-10"""

ANTI_PERIODICAL_PATTERN_YEAR_PACK = r"\byear\s+\d+\s+pack\b"
"""Pattern for year pack indicators: Year 2023 Pack"""

ANTI_PERIODICAL_PATTERN_YEAR_COMPLETE = r"\b\d{4}\s+(complete|full)\b"
"""Pattern for year complete indicators: 2023 Complete"""

ANTI_PERIODICAL_PATTERN_EDITION_NUMBER = r"\bedition\s+\d+(st|nd|rd|th)\b"
"""Pattern for numbered editions (textbooks): Edition 3rd"""

ANTI_PERIODICAL_PATTERN_ISBN = r"\bISBN\b"
"""Pattern for ISBN indicators (books)"""

ANTI_PERIODICAL_PATTERN_BOOK_FORMAT = r"\b(hardcover|paperback|ebook)\b"
"""Pattern for book format indicators"""

ANTI_PERIODICAL_PATTERN_BOOK_NUMBER = r"\bbook\s+\d+\b"
"""Pattern for book number indicators: Book 1, Book 2"""

ANTI_PERIODICAL_PATTERN_NOVEL_SERIES = r"\b(novel|trilogy|saga|series)\b"
"""Pattern for novel/series indicators"""

ANTI_PERIODICAL_PATTERN_CHAPTER = r"\bchapter\s+\d+\b"
"""Pattern for chapter indicators"""

# ==============================================================================
# RELEASE GROUP AND QUALITY PATTERNS
# ==============================================================================

RELEASE_GROUP_PATTERN_DASH = r"-[A-Z0-9]+$"
"""Pattern for dash-style release groups: -PHOTOFILEv2, -MAGAZINES"""

RELEASE_GROUP_PATTERN_BRACKETS = r"\[[A-Z0-9]+\]$"
"""Pattern for bracket-style release groups: [PHOTOFILE]"""

QUALITY_INDICATOR_PATTERN = r"\b(true\s+pdf|true\.pdf|retail|original|hq|high\s+quality|scan|digital)\b"
"""Pattern for quality indicators in filenames"""

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================


def compile_pattern(pattern: str, flags: int = re.IGNORECASE) -> re.Pattern:
    """
    Compile a regex pattern with default flags.

    Args:
        pattern: Regex pattern string
        flags: Regex flags (default: re.IGNORECASE)

    Returns:
        Compiled regex pattern
    """
    return re.compile(pattern, flags)


def compile_patterns(patterns: list[str], flags: int = re.IGNORECASE) -> list[re.Pattern]:
    """
    Compile multiple regex patterns with default flags.

    Args:
        patterns: List of regex pattern strings
        flags: Regex flags (default: re.IGNORECASE)

    Returns:
        List of compiled regex patterns
    """
    return [compile_pattern(p, flags) for p in patterns]
