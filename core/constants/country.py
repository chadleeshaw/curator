"""
Country and regional constants
"""

# ==============================================================================
# ISO Country Codes
# ==============================================================================

ISO_COUNTRIES = {
    # North America
    "US": "United States",
    "CA": "Canada",
    "MX": "Mexico",
    # Europe
    "UK": "United Kingdom",
    "DE": "Germany",
    "FR": "France",
    "IT": "Italy",
    "ES": "Spain",
    "PT": "Portugal",
    "NL": "Netherlands",
    "BE": "Belgium",
    "CH": "Switzerland",
    "AT": "Austria",
    "SE": "Sweden",
    "NO": "Norway",
    "DK": "Denmark",
    "FI": "Finland",
    "PL": "Poland",
    "CZ": "Czech Republic",
    "HU": "Hungary",
    "RO": "Romania",
    "BG": "Bulgaria",
    "GR": "Greece",
    "IE": "Ireland",
    "SK": "Slovakia",
    "HR": "Croatia",
    "SI": "Slovenia",
    "LT": "Lithuania",
    "LV": "Latvia",
    "EE": "Estonia",
    "IS": "Iceland",
    "LU": "Luxembourg",
    "MT": "Malta",
    "CY": "Cyprus",
    # Asia
    "JP": "Japan",
    "CN": "China",
    "KR": "South Korea",
    "IN": "India",
    "ID": "Indonesia",
    "TH": "Thailand",
    "MY": "Malaysia",
    "SG": "Singapore",
    "PH": "Philippines",
    "VN": "Vietnam",
    "TW": "Taiwan",
    "HK": "Hong Kong",
    # Oceania
    "AU": "Australia",
    "NZ": "New Zealand",
    # South America
    "BR": "Brazil",
    "AR": "Argentina",
    "CL": "Chile",
    "CO": "Colombia",
    "PE": "Peru",
    "VE": "Venezuela",
    # Africa
    "ZA": "South Africa",
    "EG": "Egypt",
    "NG": "Nigeria",
    "KE": "Kenya",
    # Middle East & Eastern Europe
    "RU": "Russia",
    "UA": "Ukraine",
    "TR": "Turkey",
    "SA": "Saudi Arabia",
    "AE": "United Arab Emirates",
    "IL": "Israel",
}
"""ISO 3166-1 alpha-2 country codes for region-specific editions"""


# ==============================================================================
# Language to Country Mappings
# ==============================================================================

LANGUAGE_TO_COUNTRY = {
    "English": "US",
    "German": "DE",
    "French": "FR",
    "Spanish": "ES",
    "Italian": "IT",
    "Portuguese": "PT",
    "Dutch": "NL",
    "Polish": "PL",
    "Russian": "RU",
    "Ukrainian": "UA",
    "Japanese": "JP",
    "Chinese": "CN",
    "Korean": "KR",
}
"""Default country mapping for each supported language"""

COUNTRY_TO_LANGUAGE = {
    # North America - English speaking
    "US": "English",
    "CA": "English",  # Default to English for Canada (also French)
    "UK": "English",
    "AU": "English",
    "NZ": "English",
    "IE": "English",
    "ZA": "English",  # Default to English for South Africa
    # Europe - Western
    "DE": "German",
    "AT": "German",
    "CH": "German",  # Default to German for Switzerland (also French, Italian)
    "FR": "French",
    "BE": "French",  # Default to French for Belgium (also Dutch)
    "LU": "French",  # Default to French for Luxembourg (also German)
    "ES": "Spanish",
    "MX": "Spanish",
    "AR": "Spanish",
    "CL": "Spanish",
    "CO": "Spanish",
    "PE": "Spanish",
    "VE": "Spanish",
    "IT": "Italian",
    "PT": "Portuguese",
    "BR": "Portuguese",
    "NL": "Dutch",
    # Europe - Eastern
    "PL": "Polish",
    "RU": "Russian",
    "UA": "Ukrainian",
    "CZ": "Czech",
    "HU": "Hungarian",
    "RO": "Romanian",
    "BG": "Bulgarian",
    "HR": "Croatian",
    "SI": "Slovenian",
    "SK": "Slovak",
    "LT": "Lithuanian",
    "LV": "Latvian",
    "EE": "Estonian",
    # Europe - Nordic
    "SE": "Swedish",
    "NO": "Norwegian",
    "DK": "Danish",
    "FI": "Finnish",
    "IS": "Icelandic",
    # Europe - Southern/Other
    "GR": "Greek",
    "MT": "Maltese",
    "CY": "Greek",  # Default to Greek for Cyprus (also Turkish)
    # Asia
    "JP": "Japanese",
    "CN": "Chinese",
    "TW": "Chinese",
    "HK": "Chinese",
    "KR": "Korean",
    "IN": "English",  # Default to English for India (many languages)
    "ID": "Indonesian",
    "TH": "Thai",
    "MY": "Malay",
    "SG": "English",  # Default to English for Singapore (also Chinese, Malay)
    "PH": "English",  # Default to English for Philippines (also Filipino)
    "VN": "Vietnamese",
    "BD": "Bengali",
    "PK": "Urdu",
    "NP": "Nepali",
    "LK": "Sinhala",
    "MM": "Burmese",
    "KH": "Khmer",
    "LA": "Lao",
    "MN": "Mongolian",
    "BT": "Dzongkha",
    "MO": "Chinese",
    # Middle East
    "TR": "Turkish",
    "SA": "Arabic",
    "AE": "Arabic",
    "IL": "Hebrew",
    "IR": "Persian",
    "IQ": "Arabic",
    "JO": "Arabic",
    "LB": "Arabic",
    "SY": "Arabic",
    "YE": "Arabic",
    "OM": "Arabic",
    "KW": "Arabic",
    "QA": "Arabic",
    "BH": "Arabic",
    "PS": "Arabic",
    "AM": "Armenian",
    "AZ": "Azerbaijani",
    "GE": "Georgian",
    # Africa
    "EG": "Arabic",
    "NG": "English",  # Default to English for Nigeria
    "KE": "English",  # Default to English for Kenya (also Swahili)
    # Oceania
    "FJ": "English",
    "PG": "English",
    "NC": "French",
    "PF": "French",
    "WS": "Samoan",
    "TO": "Tongan",
    "VU": "English",
    "SB": "English",
    "KI": "English",
}
"""Primary language for each country code. Used to infer language when country is detected."""


# ==============================================================================
# Country Detection Indicators
# ==============================================================================

COUNTRY_INDICATORS = {
    "UK": ["[UK]", " UK ", ".UK.", "British", "Britain"],
    "US": ["[US]", " US ", ".US.", "American", "USA"],
    "DE": ["[DE]", " DE ", ".DE.", "German", "Deutschland", "Germany"],
    "FR": ["[FR]", " FR ", ".FR.", "French", "France"],
    "ES": ["[ES]", " ES ", ".ES.", "Spain", "Spanish", "España"],
    "IT": ["[IT]", " IT ", ".IT.", "Italy", "Italian", "Italia"],
    "PT": ["[PT]", " PT ", ".PT.", "Portugal", "Portuguese"],
    "NL": ["[NL]", " NL ", ".NL.", "Netherlands", "Dutch", "Holland", "Nederland"],
    "PL": ["[PL]", " PL ", ".PL.", "Poland", "Polish", "Polska"],
    "RU": ["[RU]", " RU ", ".RU.", "Russia", "Russian"],
    "UA": ["[UA]", " UA ", ".UA.", "Ukraine", "Ukrainian"],
    "JP": ["[JP]", " JP ", ".JP.", "Japan", "Japanese"],
    "CN": ["[CN]", " CN ", ".CN.", "China", "Chinese"],
    "KR": ["[KR]", " KR ", ".KR.", "Korea", "Korean"],
    "CA": ["[CA]", " CA ", ".CA.", "Canada", "Canadian"],
    "MX": ["[MX]", " MX ", ".MX.", "Mexico", "Mexican"],
    "AU": ["[AU]", " AU ", ".AU.", "Australia", "Australian"],
    "NZ": ["[NZ]", " NZ ", ".NZ.", "New Zealand"],
    "BR": ["[BR]", " BR ", ".BR.", "Brazil", "Brazilian"],
    "AR": ["[AR]", " AR ", ".AR.", "Argentina", "Argentine"],
    "ZA": ["[ZA]", " ZA ", ".ZA.", "South Africa", "Africa"],
}
"""Keywords and patterns used to detect country from periodical titles"""
