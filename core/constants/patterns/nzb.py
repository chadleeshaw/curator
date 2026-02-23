"""
NZB-style filename metadata patterns.

Patterns for extracting country, language, edition, quality, release groups,
volume, and issue numbers from NZB filenames.
"""

# ==============================================================================
# NZB METADATA PATTERNS
# ==============================================================================

# Country/Region patterns (most specific first)
NZB_COUNTRY_PATTERNS = [
    # Match 2-letter country codes, but exclude "NO" when followed by a dot/space and digit (issue numbers like "No.5" or "No 5")
    # "IN" (India) is excluded here — it is handled separately via NZB_COUNTRY_IN_PATTERN because
    # it must be matched case-sensitively to avoid false-positives on the English word "in".
    r"\b(USA?|UK|CA|AU|NZ|DE|FR|ES|IT|NL|SE|DK|FI|JP|KR|CN|BR|MX|AR)\b",
    r"\b(NO)(?![.\s]\d)\b",  # Match NO (Norway) only if NOT followed by dot/space and digit
    r"\b(United\s+States|United\s+Kingdom|Europe|Asia|North\s+America)\b",
]
"""Patterns for detecting country/region indicators in NZB filenames"""

# India country code pattern — kept separate from NZB_COUNTRY_PATTERNS because it MUST be applied
# without re.IGNORECASE; the uppercase-only match prevents collisions with the English word "in".
NZB_COUNTRY_IN_PATTERN = r"\b(IN)\b(?=\s+[A-Z])"
"""Case-sensitive pattern for India country code.

Matches uppercase "IN" only when followed by a capitalised word (e.g. "IN USA", "IN Europe"),
which distinguishes the country code from the English preposition "in".
Must be applied with re.search(...) and NO re.IGNORECASE flag.
"""

# Language patterns
NZB_LANGUAGE_PATTERNS = [
    r"\b(English|German|French|Spanish|Italian|Portuguese|Russian|Japanese|Korean|Chinese)\b",
]
"""Patterns for detecting language indicators in NZB filenames"""

# Edition/Variant patterns
NZB_EDITION_PATTERNS = [
    r"\b(International|Global|European|Asian|Special|Limited|Digital|Print)\s+(?:Edition|Ed\.?)\b",
    r"\b(?:Edition|Ed\.?)[\s._-]*(International|Global|European|Asian|Special|Limited)\b",
]
"""Patterns for detecting edition/variant indicators in NZB filenames"""

# Quality indicators
NZB_QUALITY_PATTERNS = [
    r"\b(True\.?PDF|HQ|High\.?Quality|Retail|Original)\b",
]
"""Patterns for detecting quality indicators in NZB filenames"""

# Release group patterns (at end of filename)
NZB_RELEASE_GROUP_PATTERNS = [
    r"-([A-Z][A-Z0-9]*v?\d*)$",  # -PHOTOFILEv2, -HQ, -RETAIL (must start with letter)
    r"\[([A-Z0-9]+)\]$",  # [PHOTOFILE]
]
"""Patterns for detecting release groups in NZB filenames"""

# Volume patterns
NZB_VOLUME_PATTERN = r"(?:vol\.?|volume|v)[\s]*(\d+)\b"
"""Pattern for volume numbers: Vol.12, Volume 5, V202"""

# Issue patterns
NZB_ISSUE_PATTERN = r"\b(?:issue|no\.?|number|nr\.?|n\.?)[\s]*(\d+)\b|#[\s]*(\d+)"
"""Pattern for issue numbers: Issue 389, No. 25, N25, N.25, #45, # 45.

The \b word boundary before the keyword group prevents matching mid-word,
e.g. the trailing 'n' of 'Edition', 'Section', 'Nation', etc.
"""
