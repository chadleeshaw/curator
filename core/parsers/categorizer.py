"""
File categorization based on title keywords.
"""

from core.constants.category import CATEGORY_KEYWORDS, DEFAULT_CATEGORY


class FileCategorizer:
    """Categorize files based on title keywords"""

    def categorize(self, title: str) -> str:
        """
        Determine category based on title.

        Args:
            title: Title to categorize

        Returns:
            Category name (Periodical, Comic, Graphic Novel, Book, Document)
        """
        if not title:
            return DEFAULT_CATEGORY

        title_lower = title.lower()

        for category, keywords in CATEGORY_KEYWORDS.items():
            if any(keyword.lower() in title_lower for keyword in keywords):
                return category

        return DEFAULT_CATEGORY
