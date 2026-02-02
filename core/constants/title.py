"""
Title parsing and matching constants
"""

# ==============================================================================
# Fuzzy Matching Thresholds
# ==============================================================================

DEFAULT_FUZZY_MATCH_THRESHOLD = 80
"""Default threshold for fuzzy title matching (0-100)"""

FUZZY_DELIMITER_THRESHOLD = 0.6
"""Threshold for fuzzy matching with word delimiters (0.0-1.0)"""

# ==============================================================================
# Date Matching
# ==============================================================================

DEFAULT_DATE_TOLERANCE_DAYS = 7
"""Default tolerance in days for matching publication dates"""

DATE_PENALTY_MULTIPLIER = 2
"""Multiplier applied to date difference when calculating match score penalty"""

MAX_DATE_PENALTY = 20
"""Maximum penalty points applied for date differences in matching"""

# ==============================================================================
# Title Structure
# ==============================================================================

MIN_BASE_TITLE_WORDS = 2
"""Minimum number of words that must remain in the base title when extracting special editions"""

MIN_SPECIAL_EDITION_WORDS = 2
"""Minimum consecutive non-common words required to identify a special edition suffix"""

# ==============================================================================
# Multi-word Regional Indicators
# ==============================================================================

MULTI_WORD_REGIONAL_INDICATORS = {
    "south africa",
    "north america",
    "south america",
    "new zealand",
    "united kingdom",
    "united states",
    "hong kong",
}
"""Two-word regional indicators that should be treated as part of the base title"""

# ==============================================================================
# Multi-word Edition Variants
# ==============================================================================

MULTI_WORD_EDITION_VARIANTS = {
    "little kids",
    "young adult",
}
"""Multi-word edition variant indicators that distinguish different publications"""

# ==============================================================================
# Common Periodical Words
# ==============================================================================

COMMON_PERIODICAL_WORDS = {
    "magazine",
    "monthly",
    "weekly",
    "daily",
    "quarterly",
    "journal",
    "review",
    "digest",
    "times",
    "post",
    "news",
    "illustrated",
    "geographic",
    "swimsuit",
    "beauty",
    "style",
    "edition",
    "issue",
    "international",
    "world",
    "today",
}
"""Words commonly found in periodical titles that are part of the base name, not special edition identifiers"""

# ==============================================================================
# Country Code Normalizations
# ==============================================================================

COUNTRY_CODE_NORMALIZATIONS = {
    "USA": "US",
    "U S A": "US",
    "U.S.A": "US",
    "U.S.A.": "US",
    "U.S": "US",
    "U.S.": "US",
    "United States": "US",
    "U K": "UK",
    "U.K": "UK",
    "U.K.": "UK",
    "United Kingdom": "UK",
}
"""Mapping of country code variations to normalized forms for consistent matching"""

# ==============================================================================
# Known Periodical Titles
# ==============================================================================

KNOWN_PERIODICAL_TITLES = {
    "national geographic": "National Geographic",
    "pcgamer": "PC Gamer",
    "pc gamer": "PC Gamer",
    "pc world": "PC World",
    "mac world": "Mac World",
    "e-news": "E-News",
    "wired": "Wired",
}
"""Mapping of common periodical titles to their canonical formatting"""


# ==============================================================================
# Special Edition Detection
# ==============================================================================

SPECIAL_EDITION_KEYWORDS = [
    "special",
    "annual",
    "collector",
    "collectors",
    "holiday",
    "christmas",
    "summer special",
    "winter special",
    "spring special",
    "fall special",
    "collector's edition",
    "commemorative",
    "anniversary",
    "yearbook",
    "best of",
]
"""Keywords that indicate a special edition release"""


# ==============================================================================
# Title Cleaning
# ==============================================================================

MAX_COUNTRY_REMOVAL_PASSES = 3
"""Maximum passes to remove country codes from titles.

Titles occasionally have multiple country identifiers (e.g., "Magazine US USA United States").
Three passes handles the observed maximum while preventing infinite loops on malformed data.
"""
