"""
Edition and variant constants for distinguishing different publication types
"""

# ==============================================================================
# Ambiguous ISO Country Codes
# ==============================================================================

AMBIGUOUS_ISO_CODES = {
    "AT",  # Austria - common English word "at"
    "BE",  # Belgium - common English word "be"
    "IN",  # India - common English word "in"
    "IS",  # Iceland - common English word "is"
    "IT",  # Italy - common English word "it"
    "ME",  # Montenegro - common English word "me"
    "MY",  # Malaysia - common English word "my"
    "NO",  # Norway - common English word "no"
    "OR",  # (not ISO but sometimes used) - common English word "or"
    "SO",  # Somalia - common English word "so"
    "TO",  # Tonga - common English word "to"
}
"""
ISO country codes that are also common English words.

These are skipped during edition variant detection to avoid false positives
like "IT Professional" being classified as an Italian edition.
"""

# ==============================================================================
# Regional Edition Indicators
# ==============================================================================

NORTH_AMERICAN_EDITION_INDICATORS = {
    # US-specific indicators - these can be safely removed from queries
    # because US magazines typically don't include the country in their
    # official name (e.g., "Time" not "Time US")
    "usa",
    "us",
    "america",
}
"""US edition indicators that can be removed during query expansion"""

OTHER_REGIONAL_EDITION_INDICATORS = {
    # Directions
    "africa",
    "south",
    "north",
    "east",
    "west",
    # Regions
    "europe",
    "asia",
    "international",
    "worldwide",
    "global",
    # North America (non-US)
    "canada",
    "mexico",
    # South America
    "brazil",
    "argentina",
    "chile",
    "colombia",
    "peru",
    "venezuela",
    # Europe - Western
    "france",
    "germany",
    "italy",
    "spain",
    "portugal",
    "netherlands",
    "belgium",
    "switzerland",
    "austria",
    # Europe - Nordic
    "sweden",
    "norway",
    "denmark",
    "finland",
    "iceland",
    # Europe - Eastern
    "poland",
    "czech",
    "hungary",
    "romania",
    "bulgaria",
    "greece",
    "croatia",
    "slovenia",
    "slovakia",
    "lithuania",
    "latvia",
    "estonia",
    # British Isles
    "uk",
    "ireland",
    "scotland",
    "wales",
    # Asia
    "japan",
    "china",
    "korea",
    "india",
    "indonesia",
    "thailand",
    "malaysia",
    "singapore",
    "philippines",
    "vietnam",
    "taiwan",
    # Oceania
    "australia",
    "newzealand",
    # Africa
    "southafrica",
    "egypt",
    "nigeria",
    "kenya",
    # Middle East & Eastern Europe
    "russia",
    "ukraine",
    "turkey",
    "israel",
}
"""
Regional/country names for non-North American editions.

These should be PRESERVED during query expansion because international editions
actually include the country name as part of their identity (e.g., "Vogue France"
is different from "Vogue US").
"""

REGIONAL_EDITION_INDICATORS = NORTH_AMERICAN_EDITION_INDICATORS | OTHER_REGIONAL_EDITION_INDICATORS
"""Combined set of all regional/country edition indicators (for backward compatibility)"""


# ==============================================================================
# Edition Variant Indicators
# ==============================================================================

EDITION_VARIANT_INDICATORS = {
    # Age-specific editions (DIFFERENT publications)
    "kids",
    "little kids",
    "junior",
    "children",
    "teen",
    "young adult",
    "youth",
    # Professional/Specialized editions (DIFFERENT publications)
    "professional",
    "pro",
    # NOTE: "business" removed - too generic, often appears in publication names
    #       (e.g., "Business Weekly" is the title, not a variant)
    "enterprise",
    "developer",
    "admin",
    "advanced",
    "expert",
    # Travel/Regional variations (DIFFERENT publications)
    "traveller",
    "traveler",
    "explorer",
}
"""
Edition variant indicators that distinguish DIFFERENT publications with similar base names.

NOTE: These are NOT special editions (which are special issues of the same publication).
Format indicators like "digital", "online", "print" are excluded as they're usually metadata,
not different publications.

Examples:
  - "National Geographic Little Kids" ≠ "National Geographic" (DIFFERENT publications)
  - "PC Gamer Pro" ≠ "PC Gamer" (DIFFERENT publications)
  - "Time - Person of the Year" = "Time" (SAME publication, special issue)
  - "Magazine Digital" = "Magazine" (SAME publication, format metadata)
"""
