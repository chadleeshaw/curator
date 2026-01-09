"""
File categorization based on title keywords.
"""
from core.constants import CATEGORY_KEYWORDS


class FileCategorizer:
    """Categorize files based on title keywords"""

    def categorize(self, title: str) -> str:
        """
        Determine category based on title.

        Args:
            title: Title to categorize

        Returns:
            Category name (Magazines, Comics, Articles, News, etc.)
        """
        if not title:
            return "Magazines"

        title_lower = title.lower()

        for category, keywords in CATEGORY_KEYWORDS.items():
            if any(keyword.lower() in title_lower for keyword in keywords):
                return category

        return "Magazines"
