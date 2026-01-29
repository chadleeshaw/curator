"""
Edition and variant constants for distinguishing different publication types
"""

# ==============================================================================
# Regional Edition Indicators
# ==============================================================================

REGIONAL_EDITION_INDICATORS = {
    # Directions
    "africa",
    "south",
    "north",
    "east",
    "west",
    # Regions
    "europe",
    "asia",
    "america",
    "international",
    "worldwide",
    "global",
    # North America
    "usa",
    "uk",
    "us",
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
"""Regional/country names that indicate regional editions, not special editions"""


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
