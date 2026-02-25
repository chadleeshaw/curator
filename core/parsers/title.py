"""Title matching and deduplication."""

import logging
import re
from datetime import datetime
from typing import Dict, List, Tuple, Optional

from rapidfuzz import fuzz

from core.constants.country import ISO_COUNTRIES
from core.constants.periodical import (
    AMBIGUOUS_ISO_CODES,
    REGIONAL_PERIODICAL_INDICATORS,
    AUDIENCE_PERIODICAL_INDICATORS,
)
from core.constants.title import (
    DEFAULT_FUZZY_MATCH_THRESHOLD,
    FUZZY_DELIMITER_THRESHOLD,
    DEFAULT_DATE_TOLERANCE_DAYS,
    DATE_PENALTY_MULTIPLIER,
    MAX_DATE_PENALTY,
    MIN_BASE_TITLE_WORDS,
    MULTI_WORD_REGIONAL_INDICATORS,
    MULTI_WORD_PERIODICAL_VARIANTS,
    COMMON_PERIODICAL_WORDS,
    COUNTRY_CODE_NORMALIZATIONS,
    KNOWN_PERIODICAL_TITLES,
    SPECIAL_EDITION_KEYWORDS,
)
from core.parsers.language import LANGUAGE_INDICATORS

logger = logging.getLogger(__name__)


class TitleMatcher:
    """Fuzzy title matching for deduplication"""

    # Word delimiters for fuzzy matching
    WORD_DELIMITERS = {
        " ",
        ".",
        ",",
        "_",
        "-",
        "=",
        "(",
        ")",
        "[",
        "]",
        "|",
        '"',
        "'",
        "`",
    }

    # Hashed release patterns to reject
    HASHED_RELEASE_PATTERNS = [
        r"^[0-9a-zA-Z]{32}",  # MD5-like hash
        r"^[a-z0-9]{24}$",  # Short hash
        r"^[A-Z]{11}\d{3}$",  # NZBGeek format
        r"^[a-z]{12}\d{3}$",  # Alternative format
        r"^Backup_\d{5,}S\d{2}-\d{2}$",  # Backup filename
    ]

    # Ordered title patterns
    TITLE_PATTERNS = [
        # Pattern 1: Title - Issue No.XX - Date
        (
            r"^(?P<title>.+?)\s*[-.]\s*(?:Issue|No\.|Number)\s*(?P<issue>\d+)"
            r"\s*[-.]\s*(?P<date>.+?)(?:\s*[-.]\s*(?P<extra>.*))?$",
            "issue_date",
        ),
        # Pattern 2: Title.YYYY.MM or Title YYYY MM
        (
            r"^(?P<title>.+?)[.\s](?P<year>\d{4})[.\s](?P<month>\d{2})(?:[.\s](?P<day>\d{2}))?",
            "date_standard",
        ),
        # Pattern 3: Title Special Edition Name
        (r"^(?P<title>.+?)\s+Special\s+Edition\s+(?P<special>.+)$", "special_edition"),
        # Pattern 4: Title - Name (for special editions like "Time - Person Of The Year")
        (r"^(?P<title>.+?)\s*[-:]\s*(?P<special>[A-Z][^-:]+)$", "title_dash_special"),
        # Pattern 5: Generic title only
        (r"^(?P<title>.+?)$", "generic"),
    ]

    def __init__(self, threshold: int = DEFAULT_FUZZY_MATCH_THRESHOLD):
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
        if "password" in title_lower and "yenc" in title_lower:
            logger.debug(f"Rejected password-protected release: {title}")
            return False

        # Reject if no alphanumeric characters
        if not any(c.isalnum() for c in title):
            logger.debug(f"Rejected non-alphanumeric title: {title}")
            return False

        # Remove extension for hash checking
        title_no_ext = re.sub(r"\.[a-z0-9]{2,4}$", "", title, flags=re.IGNORECASE)

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
        title = re.sub(r"\.[a-z0-9]{2,4}$", "", title, flags=re.IGNORECASE)

        # Remove category prefixes like [Magazine], [Comic], [Newspaper], [Book]
        title = re.sub(
            r"^\[(?:Magazine|Comic|Newspaper|Book|Journal)\]\s*",
            "",
            title,
            flags=re.IGNORECASE,
        )

        # Remove website prefixes: [www.site.com] or www.site.com -
        title = re.sub(
            r"^(?:\[\s*)?(?:www\.)?[-a-z0-9-]{1,256}\."
            r"(?:[a-z]{2,6}(?:\.[a-z]{2,6})?|xn--[a-z0-9-]{4,})\b(?:\s*\]|[-\s]{1,})",
            "",
            title,
            flags=re.IGNORECASE,
        )

        # Remove website postfixes: www.site.com] at end
        title = re.sub(
            r"(?:\[\s*)?(?:www\.)?[-a-z0-9-]{1,256}\.(?:xn--[a-z0-9-]{4,}|[a-z]{2,6})(?:\s*\])?$",
            "",
            title,
            flags=re.IGNORECASE,
        )

        # Remove torrent tracker suffixes like [ettv], [rartv], [rarbg]
        title = re.sub(r"\[(?:ettv|rartv|rarbg|cttv|eztv)\]$", "", title, flags=re.IGNORECASE)

        # Remove common download/unpack prefixes
        title = re.sub(r"^(?:Unpack|Download|Get|Read)\s+", "", title, flags=re.IGNORECASE)

        # Remove language indicators (German, French, etc.) that appear as words
        # Pattern matches language names/codes with word boundaries (spaces, dots, etc.)
        language_pattern = (
            r"[\s\.](?:"
            + "|".join(
                [
                    re.escape(indicator)  # Escape special regex chars in indicators
                    for indicators in LANGUAGE_INDICATORS.values()
                    for indicator in indicators
                ]
            )
            + r")(?:[\s\.]|$)"
        )
        title = re.sub(language_pattern, " ", title, flags=re.IGNORECASE)

        # Remove format indicators BEFORE replacing dots (to catch TruePDF as one word)
        # TruePDF indicates a digitally created (text-based) PDF vs a scanned one
        title = re.sub(r"[\.\s]*TruePDF[\.\s]*", " ", title, flags=re.IGNORECASE)

        # Remove "True Pdf" format indicator (but preserve "Special Edition" after it)
        title = re.sub(r"\s+True\s+Pdf[\s\-]*", " ", title, flags=re.IGNORECASE)

        # Remove release group tags (e.g., "-LORENZ-xpost", "[hash]-xpost") - BEFORE quality removal
        title = re.sub(r"-[A-Z][A-Za-z0-9]+(?:-[a-z]+)?\[[\w]+\].*$", "", title)  # -LORENZ[hash]
        title = re.sub(r"\[[\w]+\](?:-[a-z]+)?$", "", title)  # [hash]-xpost or [hash]
        title = re.sub(r"-[A-Z][A-Za-z0-9]+(?:-[a-z]+)?$", "", title)  # -LORENZ-xpost or -LORENZ

        # Remove quality indicators (480p, 720p, 1080p, 2160p, x264, x265, h264, h265, DD5.1, 10bit, etc.)
        title = re.sub(r"[\.\s]*(480|720|1080|2160|320)[ip]", "", title, flags=re.IGNORECASE)
        title = re.sub(r"[\.\s]*[xh][\W_]?26[45]", "", title, flags=re.IGNORECASE)
        title = re.sub(r"[\.\s]*DD[\W_]?5[\W_]?1", "", title, flags=re.IGNORECASE)
        title = re.sub(r"[\.\s]*(8|10)bit", "", title, flags=re.IGNORECASE)

        # Remove common scene release tags
        release_tags = [
            "READNFO",
            "REPACK",
            "PROPER",
            "REAL",
            "RETAIL",
            "EXTENDED",
            "UNRATED",
            "COMPLETE",
        ]
        for tag in release_tags:
            title = re.sub(rf"[\.\s]*{tag}", "", title, flags=re.IGNORECASE)

        # Remove percentages (95%, etc.)
        title = re.sub(r"(\d+)%", r"\1", title)

        # Clean up multiple dots or spaces
        title = re.sub(r"\.{2,}", ".", title)
        title = re.sub(r"\s{2,}", " ", title)

        # === Formatting (formerly in standardize_title) ===

        # Replace dots and underscores with spaces
        title = title.replace(".", " ").replace("_", " ")

        # Handle camelCase by inserting spaces before uppercase letters
        # followed by lowercase letters (e.g., "NationalGeographic" -> "National Geographic")
        title = re.sub(r"([a-z])([A-Z])", r"\1 \2", title)

        # Normalize common country code variations (USA -> US, etc.)
        # Note: UK is kept as UK (not normalized to GB) for better user readability
        # Sort by length (longest first) to avoid replacing "United States" after "USA" in "USA United States"
        sorted_normalizations = sorted(COUNTRY_CODE_NORMALIZATIONS.items(), key=lambda x: len(x[0]), reverse=True)
        for long_form, short_form in sorted_normalizations:
            # Match whole words only with word boundaries
            title = re.sub(rf"\b{re.escape(long_form)}\b", short_form, title, flags=re.IGNORECASE)

        # Remove duplicate country indicators
        # Match any country code followed by itself
        title = re.sub(r"\b(US|UK|DE|FR|ES|IT|NL|AU|CA)\s+\1\b", r"\1", title, flags=re.IGNORECASE)

        # Remove issue numbers that appear as metadata: "No 123", "Issue 456", "No.789", "#42", "Vol 5", "Vol.5"
        # Must do this AFTER replacing dots with spaces
        title = re.sub(
            r"\s+(?:No|Issue|Vol|Volume|Edition)\s+\d+\s+(?:(?:19|20)\d{2}|German|Hybrid|Digital|PDF)",
            "",
            title,
            flags=re.IGNORECASE,
        )
        title = re.sub(r"\s+(?:No|Issue|Vol|Volume|Edition)\s+\d+", "", title, flags=re.IGNORECASE)  # Remove remaining
        title = re.sub(r"\s+#\d+(?:\s+(?:19|20)\d{2})?$", "", title, flags=re.IGNORECASE)

        # Remove date patterns like "-October 2016", "-Jan 2025", "August 2020" etc. (common in magazine filenames)
        # Match with or without leading dash/hyphen
        title = re.sub(
            r"\s*-?\s*(?:January|February|March|April|May|June|July|August|September|October|November|December|"
            r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s+(?:19|20)\d{2}",
            "",
            title,
            flags=re.IGNORECASE,
        )

        # Remove magazine type suffixes (often redundant metadata like "Hybrid Magazine", "Digital Magazine")
        title = re.sub(
            r"\s+(?:Hybrid|Digital|PDF|eMag|True|HQ)\s+(?:Magazine|Mag)",
            "",
            title,
            flags=re.IGNORECASE,
        )
        title = re.sub(r"\s+(magazine|mag|mag\.)$", "", title, flags=re.IGNORECASE)

        # Remove standalone format indicators (E Book, eBook, Digital, PDF, TruePDF, etc.)
        # TruePDF indicates a digitally created (text-based) PDF vs a scanned one
        title = re.sub(
            r"\s+(?:E\s*Book|eBook|Digital|PDF|ePub|True\s*PDF)(?:\s+|$)",
            " ",
            title,
            flags=re.IGNORECASE,
        )

        # Clean up multiple spaces again after replacements
        title = re.sub(r"\s+", " ", title).strip()

        # Remove trailing hyphens/dashes (left over from tag removal)
        title = re.sub(r"[-\s]+$", "", title).strip()

        # Title case (capitalize first letter of each word)
        # But preserve special formatting for common periodicals
        title_lower = title.lower()
        if title_lower in KNOWN_PERIODICAL_TITLES:
            return KNOWN_PERIODICAL_TITLES[title_lower]

        # Default title case for others
        title = title.title()

        # Preserve uppercase for common country codes (UK, US)
        # This prevents "Uk" and "Us" from appearing in titles
        title = re.sub(r"\bUk\b", "UK", title)
        title = re.sub(r"\bUs\b", "US", title)

        return title

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
                result["pattern_type"] = pattern_name
                logger.debug(f"Matched pattern '{pattern_name}' for title: {title}")
                return result

        return None

    def fuzzy_match_with_delimiters(
        self, text: str, pattern: str, threshold: float = FUZZY_DELIMITER_THRESHOLD
    ) -> Tuple[int, int, float]:
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
                candidate = " ".join(words_text[i : i + len(words_pattern)])
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
                    words.append("".join(current_word))
                    current_word = []
            else:
                current_word.append(char)

        if current_word:
            words.append("".join(current_word))

        return words

    def extract_base_title(self, title: str) -> Tuple[str, bool, str]:
        """
        Extract the base periodical title and detect if it's a special edition.

        Uses explicit pattern matching and keyword-based detection only.
        Does NOT use generic trailing-word heuristics, which produce false positives
        for multi-word publication titles.

        Args:
            title: Standardized title

        Returns:
            Tuple of (base_title, is_special_edition, special_edition_name)

        Examples:
            >>> extract_base_title("National Geographic")
            ("National Geographic", False, "")
            >>> extract_base_title("Time Special Edition Person Of The Year")
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

        # Pattern 2: Keyword-based detection using SPECIAL_EDITION_KEYWORDS
        # Only flag as special edition if an explicit keyword is found in the title
        title_lower = title.lower()
        for keyword in SPECIAL_EDITION_KEYWORDS:
            if keyword in title_lower:
                # Found a keyword — extract it as the special edition indicator
                # Try to split at the keyword position to get a base title
                keyword_pos = title_lower.find(keyword)
                base_part = title[:keyword_pos].strip()
                # Strip separators (dash, colon) from the end of the base part
                base_part = re.sub(r"[\s\-–—:]+$", "", base_part)

                if base_part:
                    # Use the keyword match and everything after as the special name
                    special_part = title[keyword_pos:].strip()
                    return (base_part, True, special_part)

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
            _, _, fuzzy_score = self.fuzzy_match_with_delimiters(title1, title2, threshold=self.threshold / 100.0)
            score = int(fuzzy_score * 100)
            is_match = fuzzy_score >= (self.threshold / 100.0)
        else:
            score = fuzz.token_set_ratio(title1.lower(), title2.lower())
            is_match = score >= self.threshold

        return is_match, score

    def _extract_issue_volume_from_title(self, title: str) -> Tuple[Optional[int], Optional[int]]:
        """
        Extract volume and issue numbers from title.

        Args:
            title: Title string to parse

        Returns:
            Tuple of (volume, issue) where either can be None
        """
        volume = None
        issue = None

        # Volume patterns: Vol 5, Volume 5, Vol. 5, V5, v5
        volume_match = re.search(r"(?:vol(?:ume)?\.?\s*|v)(\d+)", title, re.IGNORECASE)
        if volume_match:
            volume = int(volume_match.group(1))

        # Issue patterns: #123, Issue 123, No. 123, No 123
        issue_match = re.search(r"(?:#|issue\s*|no\.?\s*)(\d+)", title, re.IGNORECASE)
        if issue_match:
            issue = int(issue_match.group(1))

        return volume, issue

    def extract_periodical_variant(self, title: str) -> Optional[str]:
        """
        Extract periodical variant indicator from title.

        This identifies if the title contains a variant indicator that distinguishes it
        as a DIFFERENT periodical (not just a special issue).

        This includes:
        - Age-specific periodicals: "Kids", "Little Kids", "Junior", "Teen"
        - Professional periodicals: "Pro", "Professional", "Business"
        - Regional periodicals: "US", "UK", "DE", "France", "Germany"
        - Format periodicals: "Digital", "Online", "Print"

        IMPORTANT: This is NOT for special issues of the same publication!
        - "National Geographic Little Kids" vs "National Geographic" → DIFFERENT periodicals
        - "PC Gamer US" vs "PC Gamer UK" → DIFFERENT periodicals
        - "Time - Person of the Year" vs "Time" → SAME periodical (special issue)

        Args:
            title: Title string to parse

        Returns:
            Periodical variant string if found, None otherwise

        Examples:
            >>> _extract_periodical_variant("National Geographic Little Kids")
            "little kids"
            >>> _extract_periodical_variant("PC Gamer US")
            "us"
            >>> _extract_periodical_variant("PC Gamer UK")
            "uk"
            >>> _extract_periodical_variant("Forbes Professional")
            "professional"
            >>> _extract_periodical_variant("Time Person Of The Year")
            None  # "Person Of The Year" is a special issue, not a periodical variant
        """
        title_lower = title.lower()

        # Check for multi-word variants first (e.g., "little kids", "young adult")
        for variant in MULTI_WORD_PERIODICAL_VARIANTS:
            if variant in title_lower:
                return variant

        # Check for regional indicators (including ISO country codes)
        words = title_lower.split()
        for i, word in enumerate(words):
            # Clean punctuation from word
            clean_word = word.strip(".,;:!?()[]{}\"'")

            # Skip if this looks like "No 123" or "Vol 5" (issue/volume numbers, not periodical variants)
            if i + 1 < len(words):
                next_word = words[i + 1].strip(".,;:!?()[]{}\"'")
                if clean_word in ["no", "vol", "volume", "issue", "v"] and next_word.isdigit():
                    continue

            # Check if it's a country code (US, UK, DE, FR, etc.)
            # Skip ambiguous codes that are common English words (IT, IN, AT, etc.)
            clean_word_upper = clean_word.upper()
            if clean_word_upper in ISO_COUNTRIES and clean_word_upper not in AMBIGUOUS_ISO_CODES:
                return clean_word

            # Check if it's a regional name (france, germany, etc.)
            if clean_word in REGIONAL_PERIODICAL_INDICATORS:
                return clean_word

        # Check for single-word edition variants
        for word in words:
            # Clean punctuation from word
            clean_word = word.strip(".,;:!?()[]{}\"'")
            if clean_word in AUDIENCE_PERIODICAL_INDICATORS:
                return clean_word

        return None

    def matches_library_item_with_date_range(
        self,
        provider_title: str,
        provider_date: Optional[datetime],
        library_title: str,
        library_date: datetime,
        date_tolerance_days: int = DEFAULT_DATE_TOLERANCE_DAYS,
    ) -> Tuple[bool, int]:
        """
        Check if provider result matches library item using fuzzy title + date range + volume/issue.

        Args:
            provider_title: Title from search provider
            provider_date: Publication date from provider (may be None)
            library_title: Title from library
            library_date: Issue date from library
            date_tolerance_days: Days within month to consider match (default 7)

        Returns:
            Tuple of (is_match: bool, confidence_score: int)

        Example:
            # These would match:
            matches("PC Gamer US", "2024-01-15", "PC Gamer - United States", "2024-01-01")
            matches("Magazine - Jan 2024", "2024-01-20", "Magazine January 2024", "2024-01-01")
            matches("Comic #123", None, "Comic Issue 123", "2024-01-01")  # Issue number match

            # These would NOT match:
            matches("PC Gamer US", "2024-01-15", "PC Gamer UK", "2024-01-01")  # Different editions
            matches("Magazine", "2024-01-15", "Magazine", "2024-02-01")  # Different months
            matches("Comic #123", None, "Comic #124", "2024-01-01")  # Different issue numbers
        """
        # Step 1: Fuzzy title matching (using configured threshold)
        is_title_match, title_score = self.match(provider_title, library_title)

        if not is_title_match:
            return (False, 0)

        # Step 1.5: Check for periodical variant mismatch
        # If one title has a periodical variant and the other doesn't (or has a different one),
        # they're different periodicals despite similar base names
        provider_variant = self.extract_periodical_variant(provider_title)
        library_variant = self.extract_periodical_variant(library_title)

        # If both have periodical variants, they must match
        if provider_variant is not None and library_variant is not None:
            if provider_variant != library_variant:
                logger.debug(
                    f"Periodical variant mismatch: provider '{provider_variant}' vs library '{library_variant}'"
                )
                return (False, 0)
        # If only one has a periodical variant, they're different periodicals
        elif provider_variant is not None or library_variant is not None:
            logger.debug(
                f"Periodical variant presence mismatch: provider '{provider_variant}' vs library '{library_variant}'"
            )
            return (False, 0)

        # Step 2: Extract volume/issue numbers from both titles
        provider_vol, provider_issue = self._extract_issue_volume_from_title(provider_title)
        library_vol, library_issue = self._extract_issue_volume_from_title(library_title)

        # Step 3: Check volume/issue match if both have them
        if provider_vol is not None and library_vol is not None:
            if provider_vol != library_vol:
                # Different volumes - not a match
                logger.debug(f"Volume mismatch: provider vol {provider_vol} vs library vol {library_vol}")
                return (False, 0)

        if provider_issue is not None and library_issue is not None:
            if provider_issue != library_issue:
                # Different issue numbers - not a match
                logger.debug(f"Issue mismatch: provider issue {provider_issue} vs library issue {library_issue}")
                return (False, 0)

        # Step 4: Date range matching (if dates available)
        if provider_date is None:
            # No date provided - if we have matching volume/issue, that's good enough
            if (provider_vol is not None and provider_vol == library_vol) or (
                provider_issue is not None and provider_issue == library_issue
            ):
                logger.debug(f"Match by volume/issue: {provider_title}")
                return (True, title_score)
            # Otherwise rely on title match only
            logger.debug(f"No date or volume/issue for '{provider_title}', using title-only match")
            return (True, title_score)

        # Normalize both dates to naive (remove timezone info) for comparison
        if provider_date.tzinfo is not None:
            provider_date = provider_date.replace(tzinfo=None)
        if library_date.tzinfo is not None:
            library_date = library_date.replace(tzinfo=None)

        # Check if dates are within same month ± tolerance
        date_diff_days = abs((provider_date - library_date).days)

        # Same month check
        same_month = provider_date.year == library_date.year and provider_date.month == library_date.month

        # Adjacent dates check (within tolerance, even across month boundaries)
        within_tolerance = date_diff_days <= date_tolerance_days

        is_date_match = same_month or within_tolerance

        if is_date_match:
            # Reduce confidence score based on date distance
            date_penalty = min(date_diff_days * DATE_PENALTY_MULTIPLIER, MAX_DATE_PENALTY)
            final_score = max(title_score - date_penalty, 0)
            return (True, final_score)
        else:
            return (False, 0)

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
