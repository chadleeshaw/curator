"""
Category classification constants
"""

# ==============================================================================
# Category Names
# ==============================================================================

CATEGORY_MAGAZINES = "Magazines"
CATEGORY_COMICS = "Comics"
CATEGORY_ARTICLES = "Articles"
CATEGORY_NEWS = "News"

# List of all categories for API/UI
CATEGORIES = [
    CATEGORY_MAGAZINES,
    CATEGORY_COMICS,
    CATEGORY_NEWS,
    CATEGORY_ARTICLES,
]


# ==============================================================================
# Category Keywords
# ==============================================================================

# Category keywords for automatic file categorization
CATEGORY_KEYWORDS = {
    CATEGORY_MAGAZINES: [
        "magazine",
        "national geographic",
        "wired",
        "time",
        "newsweek",
        "economist",
        "pc gamer",
        "forbes",
    ],
    CATEGORY_COMICS: [
        "comic",
        "marvel",
        "dc",
        "graphic novel",
        "comic book",
    ],
    CATEGORY_ARTICLES: [
        "article",
        "paper",
        "journal",
        "report",
    ],
    CATEGORY_NEWS: [
        "news",
        "daily",
        "newspaper",
    ],
}
