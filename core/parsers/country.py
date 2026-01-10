"""
Country detection from filenames and titles.
Based on Readarr's IsoCountries implementation.
"""
import re
from typing import Dict, Optional

# ISO 3166-1 alpha-2 country codes + special/historical codes
ISO_COUNTRIES: Dict[str, str] = {
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
    "BD": "Bangladesh",
    "PK": "Pakistan",
    "NP": "Nepal",
    "LK": "Sri Lanka",
    "MM": "Myanmar",
    "KH": "Cambodia",
    "LA": "Laos",
    "MN": "Mongolia",
    "BT": "Bhutan",
    "MO": "Macao",

    # Middle East
    "TR": "Turkey",
    "SA": "Saudi Arabia",
    "AE": "United Arab Emirates",
    "IL": "Israel",
    "IR": "Iran",
    "IQ": "Iraq",
    "JO": "Jordan",
    "LB": "Lebanon",
    "SY": "Syria",
    "YE": "Yemen",
    "OM": "Oman",
    "KW": "Kuwait",
    "QA": "Qatar",
    "BH": "Bahrain",
    "PS": "Palestine",
    "AM": "Armenia",
    "AZ": "Azerbaijan",
    "GE": "Georgia",

    # Oceania
    "AU": "Australia",
    "NZ": "New Zealand",
    "FJ": "Fiji",
    "PG": "Papua New Guinea",
    "NC": "New Caledonia",
    "PF": "French Polynesia",
    "WS": "Samoa",
    "TO": "Tonga",
    "VU": "Vanuatu",
    "SB": "Solomon Islands",
    "KI": "Kiribati",

    # South America
    "BR": "Brazil",
    "AR": "Argentina",
    "CL": "Chile",
    "CO": "Colombia",
    "PE": "Peru",
    "VE": "Venezuela",
    "EC": "Ecuador",
    "BO": "Bolivia",
    "PY": "Paraguay",
    "UY": "Uruguay",
    "GY": "Guyana",
    "SR": "Suriname",
    "GF": "French Guiana",

    # Central America & Caribbean
    "GT": "Guatemala",
    "HN": "Honduras",
    "NI": "Nicaragua",
    "CR": "Costa Rica",
    "PA": "Panama",
    "SV": "El Salvador",
    "BZ": "Belize",
    "CU": "Cuba",
    "DO": "Dominican Republic",
    "HT": "Haiti",
    "JM": "Jamaica",
    "TT": "Trinidad and Tobago",
    "BB": "Barbados",
    "BS": "Bahamas",
    "PR": "Puerto Rico",

    # Africa
    "ZA": "South Africa",
    "EG": "Egypt",
    "NG": "Nigeria",
    "KE": "Kenya",
    "ET": "Ethiopia",
    "GH": "Ghana",
    "MA": "Morocco",
    "DZ": "Algeria",
    "TN": "Tunisia",
    "UG": "Uganda",
    "TZ": "Tanzania",
    "ZW": "Zimbabwe",
    "SD": "Sudan",
    "AO": "Angola",
    "MZ": "Mozambique",
    "MG": "Madagascar",
    "CM": "Cameroon",
    "CI": "Ivory Coast",
    "SN": "Senegal",
    "ZM": "Zambia",
    "RW": "Rwanda",
    "SO": "Somalia",
    "ML": "Mali",
    "BW": "Botswana",
    "NA": "Namibia",
    "MW": "Malawi",
    "LY": "Libya",
    "BJ": "Benin",
    "BF": "Burkina Faso",
    "NE": "Niger",
    "TD": "Chad",
    "GA": "Gabon",
    "GN": "Guinea",
    "TG": "Togo",
    "LR": "Liberia",
    "MR": "Mauritania",
    "ER": "Eritrea",
    "GM": "Gambia",
    "LS": "Lesotho",
    "SZ": "Eswatini",
    "GQ": "Equatorial Guinea",
    "MU": "Mauritius",
    "DJ": "Djibouti",
    "KM": "Comoros",
    "SC": "Seychelles",
    "CV": "Cape Verde",
    "ST": "Sao Tome and Principe",

    # Former Soviet Union
    "RU": "Russia",
    "UA": "Ukraine",
    "BY": "Belarus",
    "KZ": "Kazakhstan",
    "UZ": "Uzbekistan",
    "TM": "Turkmenistan",
    "KG": "Kyrgyzstan",
    "TJ": "Tajikistan",
    "MD": "Moldova",

    # Historical entities
    "SU": "Soviet Union",
    "YU": "Yugoslavia",
    "CS": "Czechoslovakia",

    # Regional designations
    "XE": "Europe",
    "XW": "Worldwide",
    "XU": "Unknown Country",
    "EU": "European Union",

    # Additional countries
    "AF": "Afghanistan",
    "AL": "Albania",
    "AD": "Andorra",
    "AG": "Antigua and Barbuda",
    "LC": "Saint Lucia",
    "VC": "Saint Vincent and the Grenadines",
    "GD": "Grenada",
    "DM": "Dominica",
    "KN": "Saint Kitts and Nevis",
    "LI": "Liechtenstein",
    "MC": "Monaco",
    "SM": "San Marino",
    "VA": "Vatican City",
    "BA": "Bosnia and Herzegovina",
    "ME": "Montenegro",
    "MK": "North Macedonia",
    "RS": "Serbia",
    "XK": "Kosovo",
}


def find_country(code_or_name: str) -> Optional[str]:
    """
    Find country by ISO code or name.

    Args:
        code_or_name: 2-char ISO code, 3-char code, or full country name

    Returns:
        Normalized country name or None

    Examples:
        >>> find_country("US")
        'United States'
        >>> find_country("USA")
        'United States'
        >>> find_country("United States")
        'United States'
    """
    if not code_or_name or not code_or_name.strip():
        return None

    search = code_or_name.strip().upper()

    # 2-character: Direct ISO code match
    if len(search) == 2:
        return ISO_COUNTRIES.get(search)

    # 3-character: Extract first 2 chars as code
    if len(search) == 3:
        return ISO_COUNTRIES.get(search[:2])

    # Longer: Full name match (case-insensitive)
    for code, name in ISO_COUNTRIES.items():
        if name.upper() == search:
            return name

    return None


def detect_country(text: str, default: Optional[str] = None) -> Optional[str]:
    """
    Detect country from text (filename or title).

    Args:
        text: Text to analyze
        default: Default value if no country detected

    Returns:
        Detected country code (2-letter ISO) or default

    Examples:
        >>> detect_country("Wired 2024 US Edition")
        'US'
        >>> detect_country("Magazine [UK] December 2024")
        'UK'
        >>> detect_country("Time Magazine - UK")
        'UK'
    """
    if not text:
        return default

    # Convert to uppercase for pattern matching
    text_upper = text.upper()

    # Patterns to match country codes in various contexts
    # Order matters - more specific patterns first
    patterns = [
        r'\[([A-Z]{2,3})\]',                    # [UK], [USA] in brackets
        r'\(([A-Z]{2,3})\s+EDITION\)',          # (UK Edition) in parentheses
        r'\(([A-Z]{2,3})\)',                    # (UK), (USA) in parentheses
        r'\.([A-Z]{2,3})\.',                    # .UK., .USA. with dots
        r'-([A-Z]{2,3})-',                      # -UK-, -USA- with dashes
        r'/([A-Z]{2,3})/',                      # /UK/, /USA/ in paths
        r'\s([A-Z]{2,3})\s+[-–—]',              # UK - or UK – with dash after space
        r'[-\s]([A-Z]{2,3})$',                  # - UK or  UK at end
        r'^([A-Z]{2,3})[-\s]',                  # UK- or UK  at start
        r'\b([A-Z]{2,3})\s+EDITION\b',          # Word boundary UK Edition
        r'\s([A-Z]{2,3})\s+\w+\s+EDITION',      # UK Special Edition (word between)
        r'\s([A-Z]{2,3})\s+[ÉéÈèÊê]DITION',     # UK Édition (unicode)
        r'\s([A-Z]{2,3})\)',                    # UK) in text
    ]

    for pattern in patterns:
        matches = re.findall(pattern, text_upper)
        for match in matches:
            # Check if it's a valid country code
            if match in ISO_COUNTRIES:
                # Direct match - return it as-is
                return match

            # Try as 3-letter code (e.g., USA -> US)
            if len(match) == 3 and match[:2] in ISO_COUNTRIES:
                return match[:2]

            # Check full name lookup
            country_name = find_country(match)
            if country_name:
                # Return the matched code, not the first code for the name
                # This preserves the original code format (e.g., UK, US)
                return match if len(match) == 2 else match[:2]

    # Also try matching full country names
    for code, name in ISO_COUNTRIES.items():
        # Match full country name with word boundaries
        if re.search(rf'\b{re.escape(name)}\b', text, re.IGNORECASE):
            return code

    return default
