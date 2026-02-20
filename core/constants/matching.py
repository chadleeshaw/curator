"""
Tracking match scoring weights and thresholds.

Used by TrackingMatcher to score downloaded files against existing tracking records.
"""

# ==============================================================================
# Scoring Weights
# ==============================================================================

WEIGHT_TITLE_EXACT = 100
WEIGHT_TITLE_FUZZY_HIGH = 80
WEIGHT_TITLE_ABBREVIATION = 70
WEIGHT_TITLE_FUZZY_MEDIUM = 60
WEIGHT_LANGUAGE_MATCH = 20
WEIGHT_COUNTRY_MATCH = 15
WEIGHT_CATEGORY_MATCH = 10
WEIGHT_COUNTRY_MISMATCH_PENALTY = -30

# ==============================================================================
# Match Thresholds
# ==============================================================================

MIN_SCORE_FOR_MATCH = 70
"""Minimum total score to consider a file matched to a tracking record."""

FUZZY_THRESHOLD_HIGH = 90
"""Fuzzy title ratio threshold for high-confidence matches."""

FUZZY_THRESHOLD_MEDIUM = 75
"""Fuzzy title ratio threshold for medium-confidence matches."""
