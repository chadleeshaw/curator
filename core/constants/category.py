"""
Category classification constants

Defines the five primary content categories:
- Magazines: Recurring periodicals (monthly/weekly magazines)
- Comics: Single-issue comic books
- Graphic Novels: Complete graphic novel stories
- Books: Standalone books and ebooks
- Documents: Papers, articles, reports, journals

Newsnab Category Handling:
- 7010 (Books/Mags) → Magazine
- 7030 (Books/Comics) → Comic
- 7000 (Books), 7020 (Books/EBook) → Book (rejected by validator)
- 8000 (Other), 8010 (Other/Misc) → None (requires pattern-based validation)
  * Misc can contain any type, so we use title patterns to categorize
  * Periodicals are sometimes put in Misc, so it's in ACCEPTED_NEWSNAB_CATEGORIES
  * But validation still runs pattern checks to filter books/collections
- 8050 (Other/Hashed) → Rejected (spam/obfuscated releases)
- 6000 (XXX) → None (requires pattern-based validation)
  * Adult can contain magazines, comics, or books
  * Use title patterns to determine if it's a periodical vs a book/video
"""

from core.constants.date import get_month_year_patterns, get_season_year_patterns

# ==============================================================================
# Category Names
# ==============================================================================

CATEGORY_MAGAZINE = "Magazines"
CATEGORY_COMIC = "Comics"
CATEGORY_GRAPHIC_NOVEL = "Graphic Novels"
CATEGORY_BOOK = "Books"
CATEGORY_DOCUMENT = "Documents"

# List of all categories for API/UI
CATEGORIES = [
    CATEGORY_MAGAZINE,
    CATEGORY_COMIC,
    CATEGORY_GRAPHIC_NOVEL,
    CATEGORY_BOOK,
    CATEGORY_DOCUMENT,
]

# Default category when categorization is ambiguous
DEFAULT_CATEGORY = CATEGORY_MAGAZINE


# ==============================================================================
# Newsnab Category Code Mappings
# ==============================================================================

# Map Newsnab category codes to Curator categories
# Note: Some categories require pattern-based categorization
NEWSNAB_CATEGORY_MAP = {
    "7000": CATEGORY_BOOK,  # Books (parent)
    "7010": CATEGORY_MAGAZINE,  # Books/Mags (Magazines)
    "7020": CATEGORY_BOOK,  # Books/EBook
    "7030": CATEGORY_COMIC,  # Books/Comics
    "6000": None,  # NOTE (parent) - requires pattern-based categorization (magazines, comics, or books)
    "8000": None,  # Other (parent) - requires pattern-based categorization (can be any type)
    "8010": None,  # Other/Misc - requires pattern-based categorization (can be any type)
}

# Categories that should be accepted (not rejected as non-periodicals)
# 6000 (XXX), 8000 (Other), and 8010 (Other/Misc) are included because periodicals are sometimes put there
# These categories will still undergo pattern validation to filter non-periodicals
ACCEPTED_NEWSNAB_CATEGORIES = ["6000", "7010", "7030", "8000", "8010"]

# Categories that should be rejected (books, spam, etc.)
REJECTED_NEWSNAB_CATEGORIES = ["7000", "7020", "8050"]  # Books, EBooks, Hashed/Spam


# ==============================================================================
# Category Keywords for Auto-Classification
# ==============================================================================

# Category keywords for automatic file categorization based on title
CATEGORY_KEYWORDS = {
    CATEGORY_MAGAZINE: [
        "magazine",
        "national geographic",
        "wired",
        "time",
        "newsweek",
        "economist",
        "pc gamer",
        "forbes",
        "scientific american",
        "popular science",
        "rolling stone",
        "vogue",
        "gq",
        "esquire",
        "news",
        "daily",
        "newspaper",
        "weekly",
    ],
    CATEGORY_COMIC: [
        "comic",
        "comics",
        "marvel",
        "dc comics",
        "image comics",
        "dark horse",
        "vertigo",
        "comic book",
        "comicbook",
        "batman",
        "spider-man",
        "superman",
        "x-men",
    ],
    CATEGORY_GRAPHIC_NOVEL: [
        "graphic novel",
        "omnibus",
        "anthology",
        "compendium",
    ],
    CATEGORY_BOOK: [
        "book",
        "novel",
        "hardcover",
        "paperback",
        "audiobook",
        "textbook",
    ],
    CATEGORY_DOCUMENT: [
        "article",
        "paper",
        "journal",
        "report",
        "whitepaper",
        "white paper",
        "thesis",
        "dissertation",
        "research",
        "document",
    ],
}


# ==============================================================================
# Category-Specific Validation Patterns
# ==============================================================================

# Static patterns for each category (non-date-based)
CATEGORY_PATTERNS_STATIC = {
    CATEGORY_MAGAZINE: [
        # Weekly format
        r"\b\d{4}\.\d{2}\.\d{2}\b",  # Weekly format like The Economist
        # Issue/volume patterns
        r"\b(issue|no\.?|number)\s*\d+\b",
        r"\b(vol\.?|volume)\s*\d+\b",
    ],
    CATEGORY_COMIC: [
        # Comic-specific issue patterns
        r"#\d+\b",  # "#123"
        r"\bissue\s*#?\d+\b",
        r"\bno\.?\s*\d+\b",
        # Publisher patterns
        r"\b(marvel|dc|image|dark horse|idw)\b",
    ],
    CATEGORY_GRAPHIC_NOVEL: [
        # Collection/complete story indicators
        r"\bgraphic novel\b",
        r"\bomnibus\b",
        r"\banthology\b",
        r"\bcompendium\b",
        r"\bcollected edition\b",
        r"\bvolumes?\s+\d+\s*-\s*\d+\b",  # "Volumes 1-3"
    ],
    CATEGORY_BOOK: [
        # Book-specific patterns
        r"\bbook\s+\d+\b",  # "Book 1"
        r"\b(novel|trilogy|saga|series)\b",
        r"\bedition\s+\d+(st|nd|rd|th)\b",
        r"\bISBN\b",
        r"\b(hardcover|paperback)\b",
        r"\bchapter\s+\d+\b",
    ],
    CATEGORY_DOCUMENT: [
        # Academic/professional patterns
        r"\bjournal\b",
        r"\bresearch paper\b",
        r"\bwhitepaper\b",
        r"\bthesis\b",
        r"\breport\s+\d{4}\b",
        r"\bworking paper\b",
    ],
}
"""Static category patterns (non-date-based)"""


def get_category_patterns(languages: list[str] | None = None) -> dict[str, list[str]]:
    """
    Get complete category patterns with multilingual date support.

    Args:
        languages: List of language names to include. If None, includes all supported languages.

    Returns:
        Dictionary mapping category names to lists of regex patterns

    Example:
        >>> patterns = get_category_patterns(["English", "Spanish"])
        >>> # Returns patterns for all categories with English and Spanish date support
    """
    patterns = {}
    for category, static_patterns in CATEGORY_PATTERNS_STATIC.items():
        patterns[category] = list(static_patterns)

    # Add multilingual date patterns to Magazine category
    patterns[CATEGORY_MAGAZINE].extend(get_month_year_patterns(languages))
    patterns[CATEGORY_MAGAZINE].extend(get_season_year_patterns(languages))

    return patterns


# For backwards compatibility - default to all languages
CATEGORY_PATTERNS = get_category_patterns()


# ==============================================================================
# Category File Size Ranges (in MB)
# ==============================================================================

# Expected file size ranges for validation
CATEGORY_FILE_SIZE_RANGES = {
    CATEGORY_MAGAZINE: (10, 500),  # Typical magazine PDF: 10-500 MB
    CATEGORY_COMIC: (5, 200),  # Comic book CBZ/PDF: 5-200 MB
    CATEGORY_GRAPHIC_NOVEL: (50, 1000),  # Graphic novels are larger: 50-1000 MB
    CATEGORY_BOOK: (1, 100),  # Books/ebooks: 1-100 MB
    CATEGORY_DOCUMENT: (1, 50),  # Articles/papers: 1-50 MB
}
