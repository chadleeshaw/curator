import logging
import re
from typing import Dict, List, Tuple

from fuzzywuzzy import fuzz

logger = logging.getLogger(__name__)


class TitleMatcher:
    """Fuzzy title matching for deduplication"""

    def __init__(self, threshold: int = 80):
        self.threshold = threshold

    def standardize_title(self, title: str) -> str:
        """
        Standardize a periodical title by adding proper spacing and capitalization.
        E.g., "NationalGeographic" -> "National Geographic"

        Args:
            title: Raw title from filename or database

        Returns:
            Standardized title
        """
        # First, handle camelCase by inserting spaces before uppercase letters
        # followed by lowercase letters (e.g., "NationalGeographic" -> "National Geographic")
        title = re.sub(r'([a-z])([A-Z])', r'\1 \2', title)

        # Remove "Magazine", "magazine", etc. suffixes (often redundant)
        title = re.sub(r'\s+(magazine|mag|mag\.)$', '', title, flags=re.IGNORECASE)

        # Clean up multiple spaces
        title = re.sub(r'\s+', ' ', title).strip()

        # Title case (capitalize first letter of each word)
        # But preserve special formatting for common periodicals
        common_titles = {
            'national geographic': 'National Geographic',
            'pcgamer': 'PC Gamer',
            'pc gamer': 'PC Gamer',
            'pc world': 'PC World',
            'mac world': 'Mac World',
            'e-news': 'E-News',
            'wired': 'Wired',
        }

        title_lower = title.lower()
        if title_lower in common_titles:
            return common_titles[title_lower]

        # Default title case for others
        return title.title()

    def match(self, title1: str, title2: str) -> Tuple[bool, int]:
        """
        Check if two titles are similar.

        Args:
            title1: First title
            title2: Second title

        Returns:
            Tuple of (is_match, score) where score is 0-100
        """
        score = fuzz.token_set_ratio(title1.lower(), title2.lower())
        is_match = score >= self.threshold
        return is_match, score

    def deduplicate_results(self, results: List[Dict]) -> Dict[str, List[Dict]]:
        """
        Group similar results together.

        Args:
            results: List of search results with 'title' key

        Returns:
            Dict mapping group_id to list of results in that group
        """
        groups = {}
        group_counter = 0

        for result in results:
            title = result.get("title", "")
            matched = False

            # Try to match with existing groups
            for group_id, group_results in groups.items():
                if group_results:
                    sample_title = group_results[0].get("title", "")
                    is_match, score = self.match(title, sample_title)

                    if is_match:
                        result["match_score"] = score
                        groups[group_id].append(result)
                        matched = True
                        break

            # Create new group if no match found
            if not matched:
                group_id = f"group_{group_counter}"
                group_counter += 1
                result["match_score"] = 100
                groups[group_id] = [result]

        return groups
