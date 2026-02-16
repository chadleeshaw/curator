"""
Date and month parsing constants
"""

# ==============================================================================
# Month Mappings
# ==============================================================================

# pylint: disable=duplicate-key
# Note: Some month names are shared across languages (e.g., "mai" in German/French/Norwegian)
# Later entries will override earlier ones, but this is intentional as they map to the same month
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
    "marzo": 3,  # Different from Italian marzo
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
    "aprile": 4,
    "maggio": 5,
    "giugno": 6,
    "luglio": 7,
    "settembre": 9,
    "ottobre": 10,
    # Portuguese
    "janeiro": 1,
    "fevereiro": 2,
    "março": 3,
    "marco": 3,  # ASCII alternative
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "setembro": 9,
    "outubro": 10,
    "dezembro": 12,
    # Dutch
    "januari": 1,
    "februari": 2,
    "maart": 3,
    "mei": 5,
    "augustus": 8,
    # Russian (transliterated)
    "yanvar": 1,
    "fevral": 2,
    "mart": 3,
    "aprel": 4,
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
    # Swedish
    "augusti": 8,
    # Norwegian/Danish
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

# Season month ranges for fuzzy matching
# Each season spans 3 months
SEASON_MONTHS = {
    "winter": {12, 1, 2},  # December, January, February
    "spring": {3, 4, 5},  # March, April, May
    "summer": {6, 7, 8},  # June, July, August
    "fall": {9, 10, 11},  # September, October, November
}
"""Season name to set of months that belong to that season"""

SEASON_CANONICAL_NAMES = {
    "autumn": "Fall",
    "fall": "Fall",
    "spring": "Spring",
    "summer": "Summer",
    "winter": "Winter",
}
"""Mapping of season name variants to canonical English display label."""


# ==============================================================================
# Date Validation
# ==============================================================================

MIN_VALID_YEAR = 1900
"""Minimum valid year for publication dates"""

MAX_VALID_YEAR = 2100
"""Maximum valid year for publication dates"""

DUPLICATE_DATE_THRESHOLD_DAYS = 5
"""Days threshold for considering publications as duplicates"""


# ==============================================================================
# Multilingual Month Mappings
# ==============================================================================

MONTHS_BY_LANGUAGE = {
    "English": {
        "full": [
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ],
        "abbr": [
            "jan",
            "feb",
            "mar",
            "apr",
            "may",
            "jun",
            "jul",
            "aug",
            "sep",
            "sept",
            "oct",
            "nov",
            "dec",
        ],
    },
    "German": {
        "full": [
            "januar",
            "februar",
            "märz",
            "april",
            "mai",
            "juni",
            "juli",
            "august",
            "september",
            "oktober",
            "november",
            "dezember",
        ],
        "abbr": ["marz"],  # ASCII alternative for märz
    },
    "Spanish": {
        "full": [
            "enero",
            "febrero",
            "marzo",
            "abril",
            "mayo",
            "junio",
            "julio",
            "agosto",
            "septiembre",
            "octubre",
            "noviembre",
            "diciembre",
        ],
        "abbr": [],
    },
    "French": {
        "full": [
            "janvier",
            "février",
            "mars",
            "avril",
            "mai",
            "juin",
            "juillet",
            "août",
            "septembre",
            "octobre",
            "novembre",
            "décembre",
        ],
        "abbr": ["fevrier", "aout", "decembre"],  # ASCII alternatives
    },
    "Italian": {
        "full": [
            "gennaio",
            "febbraio",
            "marzo",
            "aprile",
            "maggio",
            "giugno",
            "luglio",
            "agosto",
            "settembre",
            "ottobre",
            "novembre",
            "dicembre",
        ],
        "abbr": [],
    },
    "Portuguese": {
        "full": [
            "janeiro",
            "fevereiro",
            "março",
            "abril",
            "maio",
            "junho",
            "julho",
            "agosto",
            "setembro",
            "outubro",
            "novembro",
            "dezembro",
        ],
        "abbr": ["marco"],  # ASCII alternative for março
    },
    "Dutch": {
        "full": [
            "januari",
            "februari",
            "maart",
            "april",
            "mei",
            "juni",
            "juli",
            "augustus",
            "september",
            "oktober",
            "november",
            "december",
        ],
        "abbr": [],
    },
    "Polish": {
        "full": [
            "styczeń",
            "luty",
            "marzec",
            "kwiecień",
            "maj",
            "czerwiec",
            "lipiec",
            "sierpień",
            "wrzesień",
            "październik",
            "listopad",
            "grudzień",
        ],
        "abbr": [
            "styczen",
            "kwiecien",
            "sierpien",
            "wrzesien",
            "pazdziernik",
            "grudzien",
        ],  # ASCII alternatives
    },
    "Russian": {
        "full": [
            "yanvar",
            "fevral",
            "mart",
            "aprel",
            "may",
            "iyun",
            "iyul",
            "avgust",
            "sentyabr",
            "oktyabr",
            "noyabr",
            "dekabr",
        ],
        "abbr": [],
    },
    "Ukrainian": {
        "full": [
            "sichen",
            "liuty",
            "berezen",
            "kviten",
            "traven",
            "cherven",
            "lypen",
            "serpen",
            "veresen",
            "zhovten",
            "lystopad",
            "hruden",
        ],
        "abbr": [],
    },
}
"""Organized month names by language for regex pattern generation"""


# ==============================================================================
# Multilingual Season Mappings
# ==============================================================================

SEASONS_BY_LANGUAGE = {
    "English": ["spring", "summer", "fall", "autumn", "winter"],
    "German": ["frühling", "fruehling", "sommer", "herbst", "winter"],
    "Spanish": ["primavera", "verano", "otoño", "otono", "invierno"],
    "French": ["printemps", "été", "ete", "automne", "hiver"],
    "Italian": ["primavera", "estate", "autunno", "inverno"],
    "Portuguese": ["primavera", "verão", "verao", "outono", "inverno"],
    "Dutch": ["lente", "zomer", "herfst", "winter"],
    "Polish": ["wiosna", "lato", "jesień", "jesien", "zima"],
    "Russian": ["vesna", "leto", "osen", "zima"],
    "Ukrainian": ["vesna", "lito", "osin", "zyma"],
}
"""Organized season names by language for regex pattern generation"""


# ==============================================================================
# Regex Pattern Generators
# ==============================================================================


def get_supported_languages() -> list[str]:
    """
    Get list of languages supported for date parsing.

    Returns:
        List of language names that have month/season translations
    """
    return sorted(set(MONTHS_BY_LANGUAGE.keys()) | set(SEASONS_BY_LANGUAGE.keys()))


def get_month_regex_pattern(languages: list[str] | None = None) -> str:
    """
    Generate regex pattern for month names in specified languages.

    Args:
        languages: List of language names to include. If None, includes all supported languages.

    Returns:
        Regex pattern string matching month names (e.g., "january|febrero|januar|...")

    Example:
        >>> pattern = get_month_regex_pattern(["English", "Spanish"])
        >>> # Returns: "january|february|...|enero|febrero|..."
    """
    if languages is None:
        languages = list(MONTHS_BY_LANGUAGE.keys())

    all_months = set()
    for lang in languages:
        if lang in MONTHS_BY_LANGUAGE:
            lang_data = MONTHS_BY_LANGUAGE[lang]
            all_months.update(lang_data.get("full", []))
            all_months.update(lang_data.get("abbr", []))

    # Sort by length (longest first) to match longer names before shorter ones
    sorted_months = sorted(all_months, key=len, reverse=True)
    return "|".join(sorted_months)


def get_season_regex_pattern(languages: list[str] | None = None) -> str:
    """
    Generate regex pattern for season names in specified languages.

    Args:
        languages: List of language names to include. If None, includes all supported languages.

    Returns:
        Regex pattern string matching season names (e.g., "spring|summer|primavera|...")

    Example:
        >>> pattern = get_season_regex_pattern(["English", "Spanish"])
        >>> # Returns: "spring|summer|fall|autumn|winter|primavera|verano|..."
    """
    if languages is None:
        languages = list(SEASONS_BY_LANGUAGE.keys())

    all_seasons = set()
    for lang in languages:
        if lang in SEASONS_BY_LANGUAGE:
            all_seasons.update(SEASONS_BY_LANGUAGE[lang])

    # Sort by length (longest first) to match longer names before shorter ones
    sorted_seasons = sorted(all_seasons, key=len, reverse=True)
    return "|".join(sorted_seasons)


def get_month_year_patterns(languages: list[str] | None = None) -> list[str]:
    """
    Generate list of regex patterns for "month year" formats in multiple languages.

    Args:
        languages: List of language names to include. If None, includes all supported languages.

    Returns:
        List of regex pattern strings for various month+year formats

    Example:
        >>> patterns = get_month_year_patterns(["English"])
        >>> # Returns patterns matching "January 2024", "Jan 2024", "Jan2024", etc.
    """
    month_pattern = get_month_regex_pattern(languages)

    return [
        rf"\b({month_pattern})\s*\d{{4}}\b",  # "january 2024", "enero 2024", "jan2024"
        r"\d{1,2}[/-]\d{4}",  # "01-2024" or "1/2024"
        r"\d{1,2}\s+\d{4}",  # "01 2024" (space-separated month-year)
        r"\d{4}[/-]\d{1,2}",  # "2024-01" or "2024/1"
        r"\d{4}[\.\s]\d{1,2}",  # "2024.01" or "2024 01"
    ]


def get_season_year_patterns(languages: list[str] | None = None) -> list[str]:
    """
    Generate list of regex patterns for "season year" formats in multiple languages.

    Args:
        languages: List of language names to include. If None, includes all supported languages.

    Returns:
        List of regex pattern strings for season+year formats

    Example:
        >>> patterns = get_season_year_patterns(["English", "Spanish"])
        >>> # Returns patterns matching "Spring 2024", "Primavera 2024", etc.
    """
    season_pattern = get_season_regex_pattern(languages)

    return [
        rf"\b({season_pattern})\s+\d{{4}}\b",  # "spring 2024", "primavera 2024"
    ]
