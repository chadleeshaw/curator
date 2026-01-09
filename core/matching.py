"""Title matching and deduplication."""
import logging
import re
from typing import Dict, List, Tuple, Optional

from fuzzywuzzy import fuzz

from core.language_utils import LANGUAGE_INDICATORS

logger = logging.getLogger(__name__)


class TitleMatcher:
    """Fuzzy title matching for deduplication"""

    # Word delimiters for fuzzy matching
    WORD_DELIMITERS = {' ', '.', ',', '_', '-', '=', '(', ')', '[', ']', '|', '"', "'", '`'}

    # Hashed release patterns to reject
    HASHED_RELEASE_PATTERNS = [
        r'^[0-9a-zA-Z]{32}',  # MD5-like hash
        r'^[a-z0-9]{24}$',     # Short hash
        r'^[A-Z]{11}\d{3}$',   # NZBGeek format
        r'^[a-z]{12}\d{3}$',   # Alternative format
        r'^Backup_\d{5,}S\d{2}-\d{2}$',  # Backup filename
    ]

    # Ordered title patterns
    TITLE_PATTERNS = [
        # Pattern 1: Title - Issue No.XX - Date
        (r'^(?P<title>.+?)\s*[-.]\s*(?:Issue|No\.|Number)\s*(?P<issue>\d+)'
         r'\s*[-.]\s*(?P<date>.+?)(?:\s*[-.]\s*(?P<extra>.*))?$', 'issue_date'),

        # Pattern 2: Title.YYYY.MM or Title YYYY MM
        (r'^(?P<title>.+?)[.\s](?P<year>\d{4})[.\s](?P<month>\d{2})(?:[.\s](?P<day>\d{2}))?',
         'date_standard'),

        # Pattern 3: Title Special Edition Name
        (r'^(?P<title>.+?)\s+Special\s+Edition\s+(?P<special>.+)$', 'special_edition'),

        # Pattern 4: Title - Name (for special editions like "Time - Person Of The Year")
        (r'^(?P<title>.+?)\s*[-:]\s*(?P<special>[A-Z][^-:]+)$', 'title_dash_special'),

        # Pattern 5: Generic title only
        (r'^(?P<title>.+?)$', 'generic'),
    ]

    def __init__(self, threshold: int = 80):
        self.threshold = threshold
        # Compile regex patterns once for performance
        self._compiled_hash_patterns = [re.compile(p) for p in self.HASHED_RELEASE_PATTERNS]
        self._compiled_title_patterns = [(re.compile(p[0], re.IGNORECASE), p[1]) for p in self.TITLE_PATTERNS]

    def validate_before_parsing(self, title: str) -> bool:
        """
        Validate title before parsing to reject invalid releases.

        Args:
            title: Raw title to validate

        Returns:
            True if valid, False if should be rejected
        """
        if not title:
            return False

        title_lower = title.lower()

        # Reject password-protected releases
        if 'password' in title_lower and 'yenc' in title_lower:
            logger.debug(f"Rejected password-protected release: {title}")
            return False

        # Reject if no alphanumeric characters
        if not any(c.isalnum() for c in title):
            logger.debug(f"Rejected non-alphanumeric title: {title}")
            return False

        # Remove extension for hash checking
        title_no_ext = re.sub(r'\.[a-z0-9]{2,4}$', '', title, flags=re.IGNORECASE)

        # Reject hashed releases
        for pattern in self._compiled_hash_patterns:
            if pattern.match(title_no_ext):
                logger.debug(f"Rejected hashed release: {title}")
                return False

        return True

    def clean_release_title(self, title: str) -> str:
        """
        This should be called BEFORE standardize_title for best results.

        Args:
            title: Raw title from filename

        Returns:
            Cleaned title ready for parsing
        """
        if not title:
            return title

        # Remove file extension
        title = re.sub(r'\.[a-z0-9]{2,4}$', '', title, flags=re.IGNORECASE)

        # Remove website prefixes: [www.site.com] or www.site.com -
        title = re.sub(
            r'^(?:\[\s*)?(?:www\.)?[-a-z0-9-]{1,256}\.'
            r'(?:[a-z]{2,6}(?:\.[a-z]{2,6})?|xn--[a-z0-9-]{4,})\b(?:\s*\]|[-\s]{1,})',
            '', title, flags=re.IGNORECASE
        )

        # Remove website postfixes: www.site.com] at end
        title = re.sub(
            r'(?:\[\s*)?(?:www\.)?[-a-z0-9-]{1,256}\.(?:xn--[a-z0-9-]{4,}|[a-z]{2,6})(?:\s*\])?$',
            '', title, flags=re.IGNORECASE
        )

        # Remove torrent tracker suffixes like [ettv], [rartv], [rarbg]
        title = re.sub(r'\[(?:ettv|rartv|rarbg|cttv|eztv)\]$', '', title, flags=re.IGNORECASE)

        # Remove common download/unpack prefixes
        title = re.sub(r'^(?:Unpack|Download|Get|Read)\s+', '', title, flags=re.IGNORECASE)

        # Remove language indicators (German, French, etc.) that appear as words
        # Pattern matches language names/codes with word boundaries (spaces, dots, etc.)
        language_pattern = r'[\s\.](?:' + '|'.join([
            re.escape(indicator)  # Escape special regex chars in indicators
            for indicators in LANGUAGE_INDICATORS.values()
            for indicator in indicators
        ]) + r')(?:[\s\.]|$)'
        title = re.sub(language_pattern, ' ', title, flags=re.IGNORECASE)

        # Remove release group tags (e.g., "-LORENZ-xpost", "[hash]-xpost") - BEFORE quality removal
        title = re.sub(r'-[A-Z][A-Za-z0-9]+(?:-[a-z]+)?\[[\w]+\].*$', '', title)  # -LORENZ[hash]
        title = re.sub(r'\[[\w]+\](?:-[a-z]+)?$', '', title)  # [hash]-xpost or [hash]
        title = re.sub(r'-[A-Z][A-Za-z0-9]+(?:-[a-z]+)?$', '', title)  # -LORENZ-xpost or -LORENZ

        # Remove quality indicators (480p, 720p, 1080p, 2160p, x264, x265, h264, h265, DD5.1, 10bit, etc.)
        title = re.sub(
            r'[\.\s]*(480|720|1080|2160|320)[ip]',
            '', title, flags=re.IGNORECASE
        )
        title = re.sub(r'[\.\s]*[xh][\W_]?26[45]', '', title, flags=re.IGNORECASE)
        title = re.sub(r'[\.\s]*DD[\W_]?5[\W_]?1', '', title, flags=re.IGNORECASE)
        title = re.sub(r'[\.\s]*(8|10)bit', '', title, flags=re.IGNORECASE)

        # Remove common scene release tags
        release_tags = ['READNFO', 'REPACK', 'PROPER', 'REAL', 'RETAIL', 'EXTENDED', 'UNRATED']
        for tag in release_tags:
            title = re.sub(rf'[\.\s]*{tag}', '', title, flags=re.IGNORECASE)

        # Remove percentages (95%, etc.)
        title = re.sub(r'(\d+)%', r'\1', title)

        # Clean up multiple dots or spaces
        title = re.sub(r'\.{2,}', '.', title)
        title = re.sub(r'\s{2,}', ' ', title)

        # === Formatting (formerly in standardize_title) ===

        # Replace dots and underscores with spaces
        title = title.replace(".", " ").replace("_", " ")

        # Handle camelCase by inserting spaces before uppercase letters
        # followed by lowercase letters (e.g., "NationalGeographic" -> "National Geographic")
        title = re.sub(r"([a-z])([A-Z])", r"\1 \2", title)

        # Remove issue numbers that appear as metadata: "No 123", "Issue 456", "No.789", "#42", "Vol 5", "Vol.5"
        # Must do this AFTER replacing dots with spaces
        title = re.sub(r'\s+(?:No|Issue|Vol|Volume|Edition)\s+\d+\s+(?:(?:19|20)\d{2}|German|Hybrid|Digital|PDF)', '', title, flags=re.IGNORECASE)
        title = re.sub(r'\s+(?:No|Issue|Vol|Volume|Edition)\s+\d+', '', title, flags=re.IGNORECASE)  # Remove remaining
        title = re.sub(r'\s+#\d+(?:\s+(?:19|20)\d{2})?$', '', title, flags=re.IGNORECASE)

        # Remove magazine type suffixes (often redundant metadata like "Hybrid Magazine", "Digital Magazine")
        title = re.sub(r"\s+(?:Hybrid|Digital|PDF|eMag|True|HQ)\s+(?:Magazine|Mag)", "", title, flags=re.IGNORECASE)
        title = re.sub(r"\s+(magazine|mag|mag\.)$", "", title, flags=re.IGNORECASE)

        # Remove standalone format indicators (E Book, eBook, Digital, PDF, etc.)
        title = re.sub(r"\s+(?:E\s*Book|eBook|Digital|PDF|ePub)(?:\s+|$)", " ", title, flags=re.IGNORECASE)

        # Clean up multiple spaces again after replacements
        title = re.sub(r"\s+", " ", title).strip()

        # Title case (capitalize first letter of each word)
        # But preserve special formatting for common periodicals
        common_titles = {
            "national geographic": "National Geographic",
            "pcgamer": "PC Gamer",
            "pc gamer": "PC Gamer",
            "pc world": "PC World",
            "mac world": "Mac World",
            "e-news": "E-News",
            "wired": "Wired",
        }

        title_lower = title.lower()
        if title_lower in common_titles:
            return common_titles[title_lower]

        # Default title case for others
        return title.title()

    def parse_with_patterns(self, title: str) -> Optional[Dict[str, str]]:
        """
        Tries each pattern in priority order until one matches.

        Args:
            title: Title to parse

        Returns:
            Dict of matched groups or None if no match
        """
        for pattern, pattern_name in self._compiled_title_patterns:
            match = pattern.match(title)
            if match:
                result = match.groupdict()
                result['pattern_type'] = pattern_name
                logger.debug(f"Matched pattern '{pattern_name}' for title: {title}")
                return result

        return None

    def fuzzy_match_with_delimiters(
            self, text: str, pattern: str,
            threshold: float = 0.6) -> Tuple[int, int, float]:
        """
        Fuzzy match that respects word delimiters
        Args:
            text: Text to search in
            pattern: Pattern to search for
            threshold: Minimum match score (0.0 to 1.0)

        Returns:
            Tuple of (start_location, match_length, score)
            Returns (-1, 0, 0.0) if no match found
        """
        if not text or not pattern:
            return (-1, 0, 0.0)

        text_lower = text.lower()
        pattern_lower = pattern.lower()

        # Use fuzzywuzzy for base scoring
        base_score = fuzz.token_set_ratio(text_lower, pattern_lower) / 100.0

        if base_score >= threshold:
            # Try to find exact substring location
            idx = text_lower.find(pattern_lower)
            if idx >= 0:
                return (idx, len(pattern), base_score)

            # Try fuzzy location finding with word boundaries
            # Split by delimiters and look for best match
            words_text = self._split_by_delimiters(text)
            words_pattern = self._split_by_delimiters(pattern)

            best_match_idx = -1
            best_score = 0.0
            current_pos = 0

            for i, word in enumerate(words_text):
                # Check if this word starts a potential match
                candidate = ' '.join(words_text[i:i + len(words_pattern)])
                score = fuzz.ratio(candidate.lower(), pattern_lower) / 100.0

                if score > best_score:
                    best_score = score
                    best_match_idx = current_pos

                current_pos += len(word) + 1  # +1 for delimiter

            if best_score >= threshold and best_match_idx >= 0:
                return (best_match_idx, len(pattern), best_score)

        return (-1, 0, 0.0)

    def _split_by_delimiters(self, text: str) -> List[str]:
        """Split text by word delimiters."""
        words = []
        current_word = []

        for char in text:
            if char in self.WORD_DELIMITERS:
                if current_word:
                    words.append(''.join(current_word))
                    current_word = []
            else:
                current_word.append(char)

        if current_word:
            words.append(''.join(current_word))

        return words

    def extract_base_title(self, title: str) -> Tuple[str, bool, str]:
        """
        Extract the base periodical title and detect if it's a special edition.

        Args:
            title: Standardized title

        Returns:
            Tuple of (base_title, is_special_edition, special_edition_name)

        Examples:
            >>> extract_base_title("National Geographic")
            ("National Geographic", False, "")
            >>> extract_base_title("Sports Illustrated Swimsuit Kate Upton")
            ("Sports Illustrated Swimsuit", True, "Kate Upton")
            >>> extract_base_title("Time Magazine Person Of The Year")
            ("Time", True, "Person Of The Year")
        """
        # Pattern 1: Explicit "Special Edition" pattern with specific name
        special_pattern = r"^(.+?)\s+Special\s+Edition\s+(.+)$"
        match = re.search(special_pattern, title, re.IGNORECASE)

        if match:
            base_title = match.group(1).strip()
            special_name = match.group(2).strip()
            return (base_title, True, special_name)

        # Pattern 1b: "Special Edition" without a specific name
        special_pattern_no_name = r"^(.+?)\s+Special\s+Edition$"
        match = re.search(special_pattern_no_name, title, re.IGNORECASE)

        if match:
            base_title = match.group(1).strip()
            return (base_title, True, "Special Edition")

        # Pattern 2: Generic detection of titles with identifying suffixes
        # Strategy: Look for 2+ words at the end that appear to be proper names
        # or edition identifiers (like person names or descriptive phrases)
        #
        # Common periodical words that are part of the base title:
        common_periodical_words = {
            "magazine", "monthly", "weekly", "daily", "quarterly",
            "journal", "review", "digest", "times", "post", "news",
            "illustrated", "geographic", "swimsuit", "beauty", "style",
            "edition", "issue", "international", "world", "today"
        }

        words = title.split()

        # Need at least 3 words: "Base" + "Special" + "Name"
        if len(words) >= 3:
            # Scan from the end to find where special identifiers start
            # Special identifiers are 2+ consecutive words that are NOT common periodical words
            # BUT: Always keep at least the first 1-2 words as the base title
            min_base_words = 2 if len(words) >= 4 else 1

            special_start_idx = None
            consecutive_non_common = 0

            # Scan backwards, but don't go past min_base_words
            for i in range(len(words) - 1, min_base_words - 1, -1):
                word_lower = words[i].lower()

                # Skip numbers (years, issue numbers)
                if re.match(r"^\d+$", word_lower):
                    continue

                # If this is a common periodical word, stop counting
                if word_lower in common_periodical_words:
                    break

                consecutive_non_common += 1
                special_start_idx = i

            # If we found 2+ special words at the end, split the title
            if consecutive_non_common >= 2 and special_start_idx is not None:
                base_words = words[:special_start_idx]
                special_words = words[special_start_idx:]

                # Make sure we have a reasonable base title left
                if len(base_words) >= min_base_words:
                    base_title = " ".join(base_words)
                    special_name = " ".join(special_words)
                    return (base_title, True, special_name)

        return (title, False, "")

    def match(self, title1: str, title2: str, use_delimiters: bool = False) -> Tuple[bool, int]:
        """
        Check if two titles are similar.

        Args:
            title1: First title
            title2: Second title
            use_delimiters: Whether to use delimiter-aware fuzzy matching

        Returns:
            Tuple of (is_match, score) where score is 0-100
        """
        if use_delimiters:
            _, _, fuzzy_score = self.fuzzy_match_with_delimiters(
                title1, title2, threshold=self.threshold / 100.0
            )
            score = int(fuzzy_score * 100)
            is_match = fuzzy_score >= (self.threshold / 100.0)
        else:
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
