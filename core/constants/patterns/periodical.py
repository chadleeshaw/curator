"""
Periodical detection patterns.

Patterns for identifying periodicals vs books, including issue numbers,
volumes, and anti-periodical indicators (collections, omnibus, etc.).
"""

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
