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


