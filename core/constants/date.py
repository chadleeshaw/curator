"""
Date and month parsing constants
"""

# ==============================================================================
# Month Mappings
# ==============================================================================

MONTH_TO_NUMBER = {
    # Full month names
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    # Abbreviations
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
    # Seasons
    "spring": 3,
    "summer": 6,
    "fall": 9,
    "autumn": 9,
    "winter": 12,
}
"""Month/period name to number mapping for date parsing (case-insensitive)"""

# Derive uppercase version for OCR text matching (excluding seasons)
OCR_MONTH_NAMES = {
    k.upper(): v for k, v in MONTH_TO_NUMBER.items() if k not in ("spring", "summer", "fall", "autumn", "winter")
}
"""Month name to number mapping for OCR metadata extraction (uppercase, derived from MONTH_TO_NUMBER)"""

NUMBER_TO_MONTH = {
    1: "January",
    2: "February",
    3: "March",
    4: "April",
    5: "May",
    6: "June",
    7: "July",
    8: "August",
    9: "September",
    10: "October",
    11: "November",
    12: "December",
}
"""Month number to full English month name mapping"""

NUMBER_TO_MONTH_ABBR = {
    1: "Jan",
    2: "Feb",
    3: "Mar",
    4: "Apr",
    5: "May",
    6: "Jun",
    7: "Jul",
    8: "Aug",
    9: "Sep",
    10: "Oct",
    11: "Nov",
    12: "Dec",
}
"""Month number to abbreviated English month name mapping"""


# ==============================================================================
# Date Validation
# ==============================================================================

MIN_VALID_YEAR = 1900
"""Minimum valid year for publication dates"""

MAX_VALID_YEAR = 2100
"""Maximum valid year for publication dates"""

DUPLICATE_DATE_THRESHOLD_DAYS = 5
"""Days threshold for considering publications as duplicates"""
