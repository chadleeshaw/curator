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
from core.constants.date import MONTH_TO_NUMBER, UNKNOWN_ISSUE_DATE_YEAR
from core.parsers.language import LANGUAGE_INDICATORS

logger = logging.getLogger(__name__)

# Words that look like a title qualifier, not a person named after a hyphen.
_NOT_A_NAME_WORD = {
    "a",
    "an",
    "and",
    "of",
    "the",
    "special",
    "edition",
    "annual",
    "collector",
    "collectors",
    "holiday",
    "christmas",
    "summer",
    "winter",
    "spring",
    "fall",
    "autumn",
    "vol",
    "volume",
    "issue",
    "no",
    "number",
    "magazine",
    "mag",
    "uk",
    "us",
    "usa",
}
# Words of a special edition name, such as "Ultimate Guide", are a subtitle, not a person.
_NOT_A_NAME_WORD |= {word for keyword in SPECIAL_EDITION_KEYWORDS for word in re.findall(r"[a-z']+", keyword)}
_NOT_A_NAME_WORD |= {
    "guide",
    "guides",
    "collection",
    "handbook",
    "manual",
    "bookazine",
    "ultimate",
    "complete",
    "essential",
    "essentials",
    "history",
}
_NAME_WORD = re.compile(r"^[A-Za-z][A-Za-z'’.-]*$")
# A real site suffix. A magazine token such as "Title" is not one.
# A one-label English region suffix such as Name.uk is a magazine token
# too, read as "Name UK". www.name.uk and name.example.uk are web
# addresses, and so are example.com, name.co.uk, and site.ru.
_LABEL = r"[-a-z0-9-]{1,256}"
_GENERIC_TLD = r"info|biz|xyz|com|net|org|io|me|tv|cc|ws|to|co"
_REGION_TLD = r"uk|us|au|nz|ca"
# "it" and "no" are English words, so Make.It is not a site.
_OTHER_COUNTRY_TLD = r"fr|es|se|dk|pl|cz|be|at|ch|jp|kr|cn|de|nl|ru|eu"
_COUNTRY_TLD = rf"{_REGION_TLD}|{_OTHER_COUNTRY_TLD}|it|no"
_SECOND_LEVEL = r"uk|au|nz|br|za|jp|kr|cn"
_SITE_TLD = rf"(?:{_GENERIC_TLD}|{_COUNTRY_TLD})"
_GENERIC_HOST = rf"(?:www\.)?{_LABEL}\.(?:{_GENERIC_TLD})(?:\.(?:{_SECOND_LEVEL}))?"
_COUNTRY_HOST = rf"(?:www\.{_LABEL}|{_LABEL}\.{_LABEL})\.(?:{_COUNTRY_TLD})|{_LABEL}\.(?:{_OTHER_COUNTRY_TLD})"
_SITE_HOST = rf"(?:{_GENERIC_HOST}|{_COUNTRY_HOST})"
_LANGUAGE_WORDS = "|".join(
    re.escape(word) for word in sorted({w for ws in LANGUAGE_INDICATORS.values() for w in ws}, key=len, reverse=True)
)
_LANGUAGE_TAG = re.compile(rf"\s*[\[\(_-]\s*(?:{_LANGUAGE_WORDS})\s*[\]\)_-]", re.IGNORECASE)
_LANGUAGE_DOTTED = re.compile(rf"\.(?:{_LANGUAGE_WORDS})(?=\.)", re.IGNORECASE)
_LANGUAGE_BEFORE_EDITION = re.compile(rf"\s(?:{_LANGUAGE_WORDS})(?=\s+edition\b)", re.IGNORECASE)
# Inside brackets any suffix is a site, such as [site.club].
_BRACKETED_HOST = rf"\[\s*(?:{_LABEL}\.)+[a-z]{{2,24}}\s*\]"


def _strip_file_extension(title: str) -> str:
    """Drop a trailing file suffix. A year such as .2024 and a site suffix such as .com stay."""
    match = re.search(r"\.([A-Za-z0-9]{2,4})$", title)
    if match and not match.group(1).isdigit() and not re.fullmatch(_SITE_TLD, match.group(1), flags=re.IGNORECASE):
        return title[: match.start()]
    return title


def _collapse_plus_spellings(title: str) -> str:
    """137Plus and 137 Plus are the same magazine name as 137+."""
    return re.sub(r"(?<!\d)(\d{1,3})[\s._-]*plus\b", r"\1+", title, flags=re.IGNORECASE)


def _restore_region_case(title: str) -> str:
    """Keep UK and US uppercase after title case."""
    title = re.sub(r"\bUk\b", "UK", title)
    return re.sub(r"\bUs\b", "US", title)


def _strip_trailing_separators(value: str) -> str:
    """Drop a dash or colon left between a magazine name and a subtitle."""
    return re.sub(r"[\s\-–—:]+$", "", value).strip()


def _case_known_title(title: str) -> str:
    """Use a known magazine's casing, including when a suffix follows the name."""
    lowered = title.lower()
    exact = KNOWN_PERIODICAL_TITLES.get(lowered)
    if exact:
        return exact

    for key in sorted(KNOWN_PERIODICAL_TITLES, key=len, reverse=True):
        if not lowered.startswith(key):
            continue
        if len(lowered) > len(key) and lowered[len(key)].isalnum():
            continue
        suffix = _restore_region_case(title[len(key) :].title())
        return KNOWN_PERIODICAL_TITLES[key] + suffix

    return _restore_region_case(title.title())


def _is_plus_title(part: str) -> bool:
    """A magazine whose name is a short number and a plus, not an issue number."""
    return bool(re.fullmatch(r"\d{1,3}\+", part))


# A short number followed by one of these words is part of the name.
# ponytail: word list, add a word when a real magazine needs it.
_NUMBERED_NAME = re.compile(r"\d{1,3}\s+(?:mag(?:azine)?|minutes|days|hours|weeks|years)\b", re.IGNORECASE)


def starts_with_numbered_name(title: str) -> bool:
    """17 Magazine, 17 Magazine UK, and 20 Minutes keep their number.

    12 North Title is an issue number plus a title.
    """
    return bool(_NUMBERED_NAME.match((title or "").strip()))


def _is_numbered_magazine(title: str) -> bool:
    """The whole title is a number plus Magazine, so Magazine is not a suffix to drop."""
    return bool(re.fullmatch(r"\d{1,3}\s+mag(?:azine)?\.?", (title or "").strip(), flags=re.IGNORECASE))


def _is_issue_token(part: str) -> bool:
    """A hyphen segment that is only an issue number or a Name12 credit."""
    return bool(re.fullmatch(r"\d{1,3}", part) or re.fullmatch(r"[A-Za-z]{2,}\d{1,3}", part))


def _is_personal_name(part: str) -> bool:
    """Two to four plain words, such as "Alex Morgan". "UK" and "Special Edition" are not."""
    words = part.split()
    if not words or len(words) > 4:
        return False
    if re.fullmatch(r"\d{1,3}", words[-1]):
        words = words[:-1]
    if len(words) < 2:
        return False

    blocked = _NOT_A_NAME_WORD | set(MONTH_TO_NUMBER)
    for word in words:
        if not _NAME_WORD.match(word) or len(word) < 2 or word.lower() in blocked:
            return False
    return True


def _segment_has_title(part: str) -> bool:
    if _is_plus_title(part):
        return True
    return bool(re.search(r"[A-Za-z]", part) and not _is_issue_token(part))


def strip_issue_number_and_name(title: str) -> str:
    """Drop a leading issue number and a trailing credit from a magazine title.

    "137 - North Title - Alex Morgan" is the magazine "North Title". A credit is
    removed only when a magazine name remains. A 4-digit name such as "2600", and
    a name that is a short number followed by a plus, are kept. 137Plus and
    137 Plus collapse to that plus form. "17 Magazine" and "20 Minutes" keep their number.
    """
    if not title:
        return title

    title = _collapse_plus_spellings(title)
    parts = [part.strip() for part in re.split(r"\s+-\s+", title) if part.strip()]
    while len(parts) > 1:
        last = parts[-1]
        if _is_issue_token(last):
            parts.pop()
            continue
        if _is_personal_name(last) and any(_segment_has_title(part) for part in parts[:-1]):
            parts.pop()
            continue
        break

    if len(parts) > 1 and re.fullmatch(r"\d{1,3}", parts[0]):
        parts = parts[1:]

    title = " - ".join(parts)
    if starts_with_numbered_name(title):
        return title.strip()

    stripped = re.sub(r"^\d{1,3}\s*-\s+(?=[A-Za-z])", "", title)
    stripped = re.sub(r"^\d{1,3}\s+(?=[A-Za-z])", "", stripped).strip()
    if stripped and re.search(r"[A-Za-z]", stripped):
        title = stripped
    return title.strip()


# Vol 5, Volume 5, Vol. 5, V5. "Nov2024" is a month, not volume 2024.
_VOLUME_RE = re.compile(r"\b(?:vol(?:ume)?\.?\s*|v)(\d{1,4})\b", re.IGNORECASE)
# #123, Issue 123, No. 123, No 123. "Techno 5" is not issue 5.
_ISSUE_RE = re.compile(r"(?:#|\bissue\s*|\bno\.?\s*)(\d{1,5})\b", re.IGNORECASE)


def extract_volume_and_issue(title: str) -> Tuple[Optional[int], Optional[int]]:
    """Volume and issue numbers from a title, either of which can be None."""
    volume = _VOLUME_RE.search(title or "")
    issue = _ISSUE_RE.search(title or "")
    return (int(volume.group(1)) if volume else None, int(issue.group(1)) if issue else None)


def as_issue_int(value) -> Optional[int]:
    """A stored volume or issue number as an int, or None when it is not a plain number."""
    text = str(value).strip() if value is not None else ""
    return int(text) if text.isdigit() else None


def _merge_numbers(numbers, title: str) -> Tuple[Optional[int], Optional[int]]:
    """(volume, issue) from metadata, with each missing number taken from the title."""
    volume, issue = numbers or (None, None)
    title_volume, title_issue = extract_volume_and_issue(title)
    return (volume if volume is not None else title_volume, issue if issue is not None else title_issue)


def same_volume_and_issue(
    left: Tuple[Optional[int], Optional[int]], right: Tuple[Optional[int], Optional[int]]
) -> bool:
    """True when two (volume, issue) pairs name the same issue.

    The issue numbers have to agree, and so do the volumes: both the same, or
    neither known. "No. 1" alone never matches "Vol. 30 No. 1", since every
    volume has a No. 1.
    """
    left_volume, left_issue = left
    right_volume, right_issue = right
    if left_issue is None or left_issue != right_issue:
        return False
    return left_volume == right_volume


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

        # Before extension and site cleanup, so "137.Plus.pdf" is not read as a domain.
        title = _collapse_plus_spellings(title)

        # Remove a file extension. Leave .com and other site suffixes for the host rule.
        title = _strip_file_extension(title)

        # Remove category prefixes like [Magazine], [Comic], [Newspaper], [Book]
        title = re.sub(
            r"^\[(?:Magazine|Comic|Newspaper|Book|Journal)\]\s*",
            "",
            title,
            flags=re.IGNORECASE,
        )

        # Remove website prefixes: [www.site.com] or www.site.com -
        # The suffix has to be a real site suffix. "North.Title-Jan" and "Name.uk-Jan" are magazine names.
        title = re.sub(rf"^{_BRACKETED_HOST}[-\s]*", "", title, flags=re.IGNORECASE)
        title = re.sub(
            rf"^(?:\[\s*)?{_SITE_HOST}\b(?:\s*\]|\s+[-\s]*|-(?=[A-Za-z]))",
            "",
            title,
            flags=re.IGNORECASE,
        )

        # Remove website postfixes: www.site.com] at end
        title = re.sub(
            rf"(?:\s|\[){_SITE_HOST}\]?\s*$",
            "",
            title,
            flags=re.IGNORECASE,
        )

        # Remove torrent tracker suffixes like [ettv], [rartv], [rarbg]
        title = re.sub(r"\[(?:ettv|rartv|rarbg|cttv|eztv)\]$", "", title, flags=re.IGNORECASE)

        # Remove common download/unpack prefixes
        title = re.sub(r"^(?:Unpack|Download|Get|Read)\s+", "", title, flags=re.IGNORECASE)

        # Remove a language only where detect_language counts it: a tag such as
        # [DE], .German., -DE-, or a "German Edition" phrase. A bare "Italia" or
        # "German" does not set the language, so it stays in the title and keeps
        # that edition off the English record.
        title = _LANGUAGE_TAG.sub(" ", title)
        title = _LANGUAGE_DOTTED.sub(".", title)
        title = _LANGUAGE_BEFORE_EDITION.sub("", title)

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
            r"Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\s*(?:19|20)\d{2}",
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
        title = strip_issue_number_and_name(title)
        if not _is_numbered_magazine(title):
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

        return _case_known_title(title)

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
            base_title = _strip_trailing_separators(match.group(1))
            special_name = match.group(2).strip()
            return (base_title, True, special_name)

        # Pattern 1b: "Special Edition" without a specific name
        special_pattern_no_name = r"^(.+?)\s+Special\s+Edition$"
        match = re.search(special_pattern_no_name, title, re.IGNORECASE)

        if match:
            base_title = _strip_trailing_separators(match.group(1))
            return (base_title, True, "Special Edition")

        # Pattern 2: Keyword-based detection using SPECIAL_EDITION_KEYWORDS
        # Only flag as special edition if an explicit keyword is found in the title
        title_lower = title.lower()
        for keyword in SPECIAL_EDITION_KEYWORDS:
            if keyword in title_lower:
                # Found a keyword — extract it as the special edition indicator
                # Try to split at the keyword position to get a base title
                keyword_pos = title_lower.find(keyword)
                base_part = _strip_trailing_separators(title[:keyword_pos])

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
            score = int(fuzz.token_set_ratio(title1.lower(), title2.lower()))
            is_match = score >= self.threshold

        return is_match, score

    def _extract_issue_volume_from_title(self, title: str) -> Tuple[Optional[int], Optional[int]]:
        """Volume and issue numbers from a title, either of which can be None."""
        return extract_volume_and_issue(title)

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
        library_date: Optional[datetime],
        date_tolerance_days: int = DEFAULT_DATE_TOLERANCE_DAYS,
        provider_numbers: Optional[Tuple[Optional[int], Optional[int]]] = None,
        library_numbers: Optional[Tuple[Optional[int], Optional[int]]] = None,
    ) -> Tuple[bool, int]:
        """
        Check if provider result matches library item using fuzzy title + date range + volume/issue.

        Args:
            provider_title: Title from search provider
            provider_date: Publication date from provider (may be None)
            library_title: Title from library
            library_date: Issue date from library
            date_tolerance_days: Days within month to consider match (default 7)
            provider_numbers: (volume, issue) from the result's metadata, used before the title
            library_numbers: (volume, issue) from the library copy's metadata, used before the title

        A library date in the 1900 sentinel year means the copy has no date, so
        volume and issue numbers decide.

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
        # Stored metadata wins; the title fills in whatever it doesn't have.
        provider_vol, provider_issue = _merge_numbers(provider_numbers, provider_title)
        library_vol, library_issue = _merge_numbers(library_numbers, library_title)
        if library_date is not None and library_date.year == UNKNOWN_ISSUE_DATE_YEAR:
            library_date = None

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
        if provider_date is None or library_date is None:
            # Without a date on both sides only volume and issue numbers can tell
            # one issue from another. Matching numbers are enough even when the
            # raw fuzzy score is below threshold ("Comic Issue 123" vs "Comic #123"
            # scores 72), as long as the titles without the numbers are similar.
            # Without numbers there is no match: a bare title would match every issue.
            if not same_volume_and_issue((provider_vol, provider_issue), (library_vol, library_issue)):
                return (False, 0)
            base_provider = _ISSUE_RE.sub("", _VOLUME_RE.sub("", provider_title)).strip()
            base_library = _ISSUE_RE.sub("", _VOLUME_RE.sub("", library_title)).strip()
            base_score = int(fuzz.token_set_ratio(base_provider.lower(), base_library.lower()))
            ISSUE_MATCH_BASE_THRESHOLD = 60
            if base_score >= ISSUE_MATCH_BASE_THRESHOLD:
                logger.debug(f"Match by volume/issue (base score {base_score}): {provider_title}")
                return (True, base_score)
            return (False, 0)

        # Fuzzy title must pass threshold before proceeding to date comparison
        if not is_title_match:
            return (False, 0)

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
