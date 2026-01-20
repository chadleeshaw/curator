"""
Date and month parsing constants
"""

# ==============================================================================
# Month Mappings
# ==============================================================================

MONTH_TO_NUMBER = {
    # Full month names - English
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
    # Abbreviations - English
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
    # German
    "januar": 1,
    "februar": 2,
    "märz": 3,
    "marz": 3,  # ASCII alternative
    "mai": 5,
    "juni": 6,
    "juli": 7,
    "oktober": 10,
    "dezember": 12,
    # Spanish
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
    # French
    "janvier": 1,
    "février": 2,
    "fevrier": 2,  # ASCII alternative
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "août": 8,
    "aout": 8,  # ASCII alternative
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "décembre": 12,
    "decembre": 12,  # ASCII alternative
    # Italian
    "gennaio": 1,
    "febbraio": 2,
    "marzo": 3,
    "aprile": 4,
    "maggio": 5,
    "giugno": 6,
    "luglio": 7,
    "agosto": 8,
    "settembre": 9,
    "ottobre": 10,
    "novembre": 11,
    "dicembre": 12,
    # Portuguese
    "janeiro": 1,
    "fevereiro": 2,
    "março": 3,
    "marco": 3,  # ASCII alternative
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
    # Dutch
    "januari": 1,
    "februari": 2,
    "maart": 3,
    "mei": 5,
    "juni": 6,
    "juli": 7,
    "augustus": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "december": 12,
    # Russian (transliterated)
    "yanvar": 1,
    "fevral": 2,
    "mart": 3,
    "aprel": 4,
    "mai": 5,
    "iyun": 6,
    "iyul": 7,
    "avgust": 8,
    "sentyabr": 9,
    "oktyabr": 10,
    "noyabr": 11,
    "dekabr": 12,
    # Polish
    "styczeń": 1,
    "styczen": 1,  # ASCII alternative
    "luty": 2,
    "marzec": 3,
    "kwiecień": 4,
    "kwiecien": 4,  # ASCII alternative
    "maj": 5,
    "czerwiec": 6,
    "lipiec": 7,
    "sierpień": 8,
    "sierpien": 8,  # ASCII alternative
    "wrzesień": 9,
    "wrzesien": 9,  # ASCII alternative
    "październik": 10,
    "pazdziernik": 10,  # ASCII alternative
    "listopad": 11,
    "grudzień": 12,
    "grudzien": 12,  # ASCII alternative
    # Ukrainian (transliterated)
    "sichen": 1,
    "liuty": 2,
    "berezen": 3,
    "kviten": 4,
    "traven": 5,
    "cherven": 6,
    "lypen": 7,
    "serpen": 8,
    "veresen": 9,
    "zhovten": 10,
    "lystopad": 11,
    "hruden": 12,
    # Swedish (common in Scandinavia)
    "januari": 1,
    "februari": 2,
    "mars": 3,
    "april": 4,
    "maj": 5,
    "juni": 6,
    "juli": 7,
    "augusti": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "december": 12,
    # Norwegian/Danish (very similar)
    "januar": 1,
    "februar": 2,
    "mars": 3,
    "april": 4,
    "mai": 5,
    "juni": 6,
    "juli": 7,
    "august": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "desember": 12,
    # Seasons (English)
    "spring": 3,
    "summer": 6,
    "fall": 9,
    "autumn": 9,
    "winter": 12,
}
"""Month/period name to number mapping for date parsing (case-insensitive)"""

# Derive uppercase version for OCR text matching (excluding seasons)
OCR_MONTH_NAMES = {
    k.upper(): v
    for k, v in MONTH_TO_NUMBER.items()
    if k not in ("spring", "summer", "fall", "autumn", "winter")
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
