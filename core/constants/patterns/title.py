"""
Title parsing and cleanup patterns.

Patterns for extracting titles from various filename formats
and cleaning up title strings.
"""

# ==============================================================================
# TITLE EXTRACTION PATTERNS
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

# Patterns for volume/issue WITHOUT year (for magazines that use volume numbering)
TITLE_PATTERN_VOLUME_ONLY = r"^(.+?)[\.\s\-]+vol\.?[\.\s]*(\d{1,4})(?:[\.\s\-]+(.+))?$"
"""Pattern for Title Vol.XXX (no year): Magazine Vol.260"""

TITLE_PATTERN_ISSUE_ONLY = r"^(.+?)[\.\s\-]+(?:no\.?|number|issue|#)[\.\s]*(\d{1,4})(?:[\.\s\-]+(.+))?$"
"""Pattern for Title No.XXX (no year): PC Gamer Issue 405"""

TITLE_PATTERN_LEADING_ISSUE = r"^(\d{1,4})\s*-\s*(.+?)(?:\s*-\s*vol\.?[\.\s]*(\d{1,4}))?(?:\s*-\s*(.+))?$"
"""Pattern for XXX - Title (leading issue number): 260 - Magazine - Vol.260 - Cover Model
Groups: (1) issue number, (2) title, (3) volume if present, (4) suffix if present"""

TITLE_PATTERN_DATE_ONLY_COMPACT = r"^([A-Za-z]+)(\d{4})$"
"""Pattern for date-only filename (compact): Apr2001"""

TITLE_PATTERN_DATE_ONLY_SPACED = r"^([A-Za-z]+)\s+(\d{4})$"
"""Pattern for date-only filename (spaced): April 2001"""

TITLE_PATTERN_TIMESTAMP_ID = r"^(.+?)\s*\((\d{4})(\d{2})(\d{2})[_\-]?\d{0,6}\)$"
"""Pattern for Title (YYYYMMDD_HHMMSS) download timestamps: Magazine (20260205_235420)"""

# ==============================================================================
# TITLE CLEANUP PATTERNS
# ==============================================================================

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
