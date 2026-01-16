"""
Tracking matcher for determining if a downloaded file belongs to an existing tracking record.
Uses weighted scoring to match parsed metadata against tracking attributes.
"""

import logging
import re
from typing import Dict, Optional, Tuple
from dataclasses import dataclass

from fuzzywuzzy import fuzz

logger = logging.getLogger(__name__)


# Scoring weights for different matching criteria
WEIGHT_TITLE_EXACT = 100
WEIGHT_TITLE_FUZZY_HIGH = 80
WEIGHT_TITLE_ABBREVIATION = 70
WEIGHT_TITLE_FUZZY_MEDIUM = 60
WEIGHT_LANGUAGE_MATCH = 20
WEIGHT_COUNTRY_MATCH = 15
WEIGHT_CATEGORY_MATCH = 10

# Thresholds
MIN_SCORE_FOR_MATCH = 70  # Minimum score to consider it a match
FUZZY_THRESHOLD_HIGH = 90  # High confidence fuzzy match
FUZZY_THRESHOLD_MEDIUM = 75  # Medium confidence fuzzy match


@dataclass
class MatchScore:
    """Result of a tracking match attempt"""

    tracking_id: int
    tracking_title: str
    score: int
    is_match: bool
    breakdown: Dict[str, int]  # Detailed score breakdown


class TrackingMatcher:
    """
    Match downloaded files to existing tracking records using weighted scoring.

    This helps prevent creating duplicate tracking when a downloaded file
    should belong to an existing tracking record.
    """

    def __init__(self, min_score: int = MIN_SCORE_FOR_MATCH):
        """
        Initialize the tracking matcher.

        Args:
            min_score: Minimum score required to consider a match (0-100)
        """
        self.min_score = min_score

        # Common title prefixes/suffixes to strip for matching
        self.title_noise = [
            r"^\[Magazine\]\s*",
            r"^\[Comic\]\s*",
            r"^\[Newspaper\]\s*",
            r"^\[Book\]\s*",
            r"\s+Magazine$",
            r"\s+Comic$",
            r"\s+Newspaper$",
        ]
        self.compiled_noise_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.title_noise
        ]

        # Country code normalizations
        self.country_normalizations = {
            "USA": "US",
            "U.S.A": "US",
            "U.S.A.": "US",
            "U.S.": "US",
            "United States": "US",
            "UK": "GB",
            "U.K": "GB",
            "U.K.": "GB",
            "United Kingdom": "GB",
        }

    def normalize_title(self, title: str) -> str:
        """
        Normalize a title for matching by removing noise and standardizing format.

        Args:
            title: Raw title string

        Returns:
            Normalized title
        """
        if not title:
            return ""

        normalized = title.strip()

        # Remove common prefixes/suffixes
        for pattern in self.compiled_noise_patterns:
            normalized = pattern.sub("", normalized)

        # Normalize whitespace
        normalized = re.sub(r"\s+", " ", normalized).strip()

        # Normalize country codes in title
        # (handle dots by replacing them with spaces first for matching)
        for long_form, short_form in self.country_normalizations.items():
            # Match whole words only, case insensitive
            # Replace dots with optional spaces for matching
            # (e.g., U.S.A. or U S A or USA)
            pattern_str = re.escape(long_form).replace(r"\.", r"[.\s]*")
            normalized = re.sub(
                rf"\b{pattern_str}\b", short_form, normalized, flags=re.IGNORECASE
            )

        # Clean up any trailing dots after normalization
        normalized = re.sub(r"\.+$", "", normalized).strip()

        return normalized

    def normalize_country(self, country: Optional[str]) -> Optional[str]:
        """
        Normalize country code to standard form.

        Args:
            country: Country code or name

        Returns:
            Normalized country code or None
        """
        if not country:
            return None

        country_clean = country.strip()

        # Try exact match first (case-insensitive)
        for long_form, short_form in self.country_normalizations.items():
            if country_clean.upper() == long_form.upper():
                return short_form

        # If no match, return uppercase version
        return country_clean.upper()

    def generate_abbreviation(self, title: str) -> str:
        """
        Generate an abbreviation from a title by taking first letters of significant words.

        Args:
            title: Title to generate abbreviation from

        Returns:
            Lowercase abbreviation string

        Examples:
            >>> generate_abbreviation("National Geographic")
            "ng"
            >>> generate_abbreviation("PC Gamer")
            "pg"
        """
        if not title:
            return ""

        # Normalize and split into words
        normalized = self.normalize_title(title)
        words = normalized.lower().split()

        # Skip common filler words
        skip_words = {"the", "a", "an", "and", "or", "of", "magazine", "mag"}
        significant_words = [w for w in words if w not in skip_words and w.strip()]

        # Take first letter of each significant word
        abbreviation = "".join(word[0] for word in significant_words if word)

        return abbreviation

    def calculate_title_score(
        self, parsed_title: str, tracking_title: str
    ) -> Tuple[int, str]:
        """
        Calculate similarity score between two titles.

        Args:
            parsed_title: Title from parsed file
            tracking_title: Title from tracking record

        Returns:
            Tuple of (score, match_type)
        """
        # Normalize both titles
        norm_parsed = self.normalize_title(parsed_title).lower()
        norm_tracking = self.normalize_title(tracking_title).lower()

        # Exact match
        if norm_parsed == norm_tracking:
            return (WEIGHT_TITLE_EXACT, "exact")

        # Check for abbreviation match if parsed title is very short (2-4 chars)
        # This works well for multi-word titles: "ng" -> "National Geographic"
        if 2 <= len(norm_parsed) <= 4 and norm_parsed.isalpha():
            tracking_abbreviation = self.generate_abbreviation(tracking_title)
            if tracking_abbreviation and norm_parsed == tracking_abbreviation:
                logger.info(
                    f"Abbreviation match: '{parsed_title}' matches '{tracking_title}' (abbreviation: {tracking_abbreviation})"
                )
                return (
                    WEIGHT_TITLE_ABBREVIATION,
                    f"abbreviation ({norm_parsed} -> {tracking_title})",
                )

        # Fuzzy matching
        fuzzy_score = fuzz.ratio(norm_parsed, norm_tracking)

        if fuzzy_score >= FUZZY_THRESHOLD_HIGH:
            return (WEIGHT_TITLE_FUZZY_HIGH, f"fuzzy_high ({fuzzy_score})")
        if fuzzy_score >= FUZZY_THRESHOLD_MEDIUM:
            return (WEIGHT_TITLE_FUZZY_MEDIUM, f"fuzzy_medium ({fuzzy_score})")

        # Try token sort ratio for word order variations
        token_score = fuzz.token_sort_ratio(norm_parsed, norm_tracking)
        if token_score >= FUZZY_THRESHOLD_HIGH:
            return (WEIGHT_TITLE_FUZZY_HIGH, f"token_sort ({token_score})")
        if token_score >= FUZZY_THRESHOLD_MEDIUM:
            return (WEIGHT_TITLE_FUZZY_MEDIUM, f"token_sort_medium ({token_score})")

        # Not a good match
        return (0, f"no_match (ratio:{fuzzy_score}, token:{token_score})")

    def match_to_tracking(
        self,
        parsed_title: str,
        tracking_title: str,
        parsed_language: Optional[str] = None,
        tracking_language: Optional[str] = None,
        parsed_country: Optional[str] = None,
        tracking_country: Optional[str] = None,
        parsed_category: Optional[str] = None,
        tracking_category: Optional[str] = None,
    ) -> Tuple[int, Dict[str, int]]:
        """
        Calculate match score between parsed file metadata and tracking record.

        Args:
            parsed_title: Title from parsed file
            tracking_title: Title from tracking record
            parsed_language: Language from parsed file
            tracking_language: Language from tracking record
            parsed_country: Country from parsed file
            tracking_country: Country from tracking record
            parsed_category: Category from parsed file
            tracking_category: Category from tracking record

        Returns:
            Tuple of (total_score, breakdown_dict)
        """
        breakdown = {}
        total_score = 0

        # Title matching (most important)
        title_score, match_type = self.calculate_title_score(
            parsed_title, tracking_title
        )
        breakdown["title"] = title_score
        breakdown["title_match_type"] = match_type
        total_score += title_score

        # Language matching
        if parsed_language and tracking_language:
            # Normalize language (e.g., "English" == "english")
            norm_parsed_lang = parsed_language.lower().strip()
            norm_tracking_lang = tracking_language.lower().strip()

            if norm_parsed_lang == norm_tracking_lang:
                breakdown["language"] = WEIGHT_LANGUAGE_MATCH
                total_score += WEIGHT_LANGUAGE_MATCH
            else:
                breakdown["language"] = 0
        else:
            # No language info, assume neutral
            breakdown["language"] = 0

        # Country matching
        if parsed_country or tracking_country:
            norm_parsed_country = self.normalize_country(parsed_country)
            norm_tracking_country = self.normalize_country(tracking_country)

            if norm_parsed_country and norm_tracking_country:
                if norm_parsed_country == norm_tracking_country:
                    breakdown["country"] = WEIGHT_COUNTRY_MATCH
                    total_score += WEIGHT_COUNTRY_MATCH
                else:
                    # Explicit country mismatch - regional editions should be separate trackings
                    # Set score to 0 to prevent matching entirely
                    breakdown["country"] = "mismatch"
                    total_score = 0
            else:
                # One or both not specified, neutral
                breakdown["country"] = 0
        else:
            breakdown["country"] = 0

        # Category matching
        if parsed_category and tracking_category:
            # Normalize category
            norm_parsed_cat = parsed_category.lower().strip()
            norm_tracking_cat = tracking_category.lower().strip()

            if norm_parsed_cat == norm_tracking_cat:
                breakdown["category"] = WEIGHT_CATEGORY_MATCH
                total_score += WEIGHT_CATEGORY_MATCH
            else:
                breakdown["category"] = 0
        else:
            breakdown["category"] = 0

        return (total_score, breakdown)

    def find_best_match(
        self,
        parsed_title: str,
        tracking_records: list,
        parsed_language: Optional[str] = None,
        parsed_country: Optional[str] = None,
        parsed_category: Optional[str] = None,
    ) -> Optional[MatchScore]:
        """
        Find the best matching tracking record for a parsed file.

        Args:
            parsed_title: Title from parsed file
            tracking_records: List of MagazineTracking records to check
            parsed_language: Language from parsed file
            parsed_country: Country from parsed file (can be in title or metadata)
            parsed_category: Category from parsed file

        Returns:
            MatchScore object if a match is found, None otherwise
        """
        if not tracking_records:
            logger.debug("No tracking records to match against")
            return None

        best_match = None
        best_score = 0

        logger.debug(
            "Matching parsed title '%s' against %d tracking records",
            parsed_title,
            len(tracking_records),
        )

        for tracking in tracking_records:
            score, breakdown = self.match_to_tracking(
                parsed_title=parsed_title,
                tracking_title=tracking.title,
                parsed_language=parsed_language,
                tracking_language=tracking.language,
                parsed_country=parsed_country,
                tracking_country=tracking.country,
                parsed_category=parsed_category,
                tracking_category=tracking.category,
            )

            logger.debug(
                "  Tracking '%s' (ID: %d): score=%d, breakdown=%s",
                tracking.title,
                tracking.id,
                score,
                breakdown,
            )

            if score > best_score:
                best_score = score
                best_match = MatchScore(
                    tracking_id=tracking.id,
                    tracking_title=tracking.title,
                    score=score,
                    is_match=(score >= self.min_score),
                    breakdown=breakdown,
                )

        if best_match and best_match.is_match:
            logger.info(
                "Found tracking match: '%s' -> '%s' (ID: %d, score: %d, breakdown: %s)",
                parsed_title,
                best_match.tracking_title,
                best_match.tracking_id,
                best_match.score,
                best_match.breakdown,
            )
            return best_match
        if best_match:
            logger.info(
                "Best match below threshold: '%s' -> '%s' (ID: %d, score: %d/%d, breakdown: %s)",
                parsed_title,
                best_match.tracking_title,
                best_match.tracking_id,
                best_match.score,
                self.min_score,
                best_match.breakdown,
            )
        else:
            logger.debug("No matches found for '%s'", parsed_title)

        return None
