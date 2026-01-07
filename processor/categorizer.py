"""
File categorization based on title keywords.
Maps periodical titles to categories like Magazines, Comics, Articles, or News.
"""
import logging

from core.constants import CATEGORY_KEYWORDS

logger = logging.getLogger(__name__)


class FileCategorizer:
    """Categorize files based on title keywords"""

    def categorize(self, title: str) -> str:
        """
        Categorize file based on title keywords.

        Args:
            title: File or periodical title

        Returns:
            Category name (default: "Magazines")
        """
        title_lower = title.lower()

        for category, keywords in CATEGORY_KEYWORDS.items():
            for keyword in keywords:
                if keyword in title_lower:
                    return category

        return "Magazines"
