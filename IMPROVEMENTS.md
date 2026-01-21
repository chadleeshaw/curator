# Curator Workflow Improvements

Three key improvement areas to enhance Curator's accuracy and organization capabilities.

## Table of Contents

1. [Preventing Non-Periodical Downloads](#1-preventing-non-periodical-downloads)
2. [Comprehensive NZB Name Parsing](#2-comprehensive-nzb-name-parsing)
3. [Better Download/Organized Folder Organization](#3-better-downloadorganized-folder-organization)

---

## 1. Preventing Non-Periodical Downloads

### Problem

Currently, the workflow at **Step 3 (Search Providers)** and **Step 4a (Issue Discovery)** doesn't validate whether search results are actually periodicals. This can lead to downloading:

- Books/novels with similar titles
- One-time publications (not recurring issues)
- Compilations/collections
- Wrong content types

### Current Flow (from WORKFLOW.md)

```
Step 3: Search Providers
  → Queries Newsnab/RSS providers
  → Filters by language/country/edition
  → NO CONTENT TYPE VALIDATION

Step 4a: Issue Discovery - Record Results
  → Parse metadata from search results
  → Generate fuzzy match group
  → Create DiscoveredIssue record
  → NO PERIODICAL VALIDATION
```

### Proposed Solution

Add a **Periodical Validation Layer** between Steps 3 and 4a:

#### A. Category/Classification Validation

**Implementation Location:** `services/issue_discovery.py` in `record_search_results()` method (line ~44)

**Add validation before recording discovered issues:**

```python
def _validate_is_periodical(self, search_result: Dict[str, Any]) -> bool:
    """
    Validate that a search result represents a periodical issue.

    Checks:
    - Newsnab category (should be magazines/periodicals, NOT books)
    - Title patterns (issue numbers, dates, volume numbers)
    - Publisher patterns (known periodical publishers)
    - Recurring publication indicators

    Returns:
        True if likely a periodical, False otherwise
    """
    # Check Newsnab category
    category = search_result.get("category", "")
    if category:
        # Books categories to reject
        book_categories = [
            "7000",  # Books
            "7010",  # Books/Mags (ambiguous, needs title check)
            "7020",  # Books/EBook
            "7030",  # Books/Comics
        ]
        # Periodical categories to accept
        periodical_categories = [
            "8010",  # Mags
            "8020",  # Mags/Magazines
        ]

        if any(cat in category for cat in book_categories):
            logger.debug(f"Rejecting: Book category detected: {category}")
            return False

        if any(cat in category for cat in periodical_categories):
            return True  # Explicit periodical category

    # Check title for periodical indicators
    title = search_result.get("title", "")
    return self._has_periodical_patterns(title)


def _has_periodical_patterns(self, title: str) -> bool:
    """
    Check if title contains patterns typical of periodicals.

    Periodical indicators:
    - Date patterns: "January 2024", "Jan 2024", "01.2024"
    - Issue numbers: "#123", "Issue 45", "No. 67"
    - Volume numbers: "Vol. 12", "Volume 5"
    - Combined: "Vol 12 No 3", "2024-01"

    Anti-patterns (books/collections):
    - "Complete Collection"
    - "Anthology"
    - "Omnibus"
    - Novel-like titles without dates
    """
    import re
    from core.constants.date import MONTH_TO_NUMBER

    # Anti-patterns: These indicate NOT a periodical
    anti_patterns = [
        r'\b(complete|full|entire)\s+(collection|series)\b',
        r'\banthology\b',
        r'\bomnibus\b',
        r'\bcompendium\b',
        r'\b(volumes?|issues?)\s+\d+\s*-\s*\d+\b',  # "Volumes 1-5" (collection)
        r'\byear\s+\d+\s+pack\b',  # "Year 2023 Pack" (collection)
    ]

    title_lower = title.lower()
    for pattern in anti_patterns:
        if re.search(pattern, title_lower, re.IGNORECASE):
            logger.debug(f"Rejecting: Anti-pattern found in '{title}': {pattern}")
            return False

    # Periodical patterns: These indicate it IS a periodical
    periodical_patterns = [
        # Date patterns
        r'\b(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d{4}\b',
        r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\.?\s*\d{4}\b',
        r'\b\d{1,2}[/-]\d{4}\b',  # "01-2024" or "1/2024"
        r'\b\d{4}[/-]\d{1,2}\b',  # "2024-01" or "2024/1"

        # Issue/Number patterns
        r'\b(issue|no\.?|number|nr\.?)\s*\d+\b',
        r'#\d+',

        # Volume patterns
        r'\b(vol\.?|volume)\s*\d+',

        # Combined volume + issue
        r'\bv\d+\s+(i|n|no\.?)\d+\b',  # "V12 N3"
    ]

    for pattern in periodical_patterns:
        if re.search(pattern, title_lower, re.IGNORECASE):
            logger.debug(f"Accepting: Periodical pattern found in '{title}': {pattern}")
            return True

    # If no clear indicators, be conservative and reject
    logger.debug(f"Rejecting: No clear periodical patterns in '{title}'")
    return False
```

**Integration in `record_search_results()`:**

```python
def record_search_results(
    self, tracking_id: int, search_results: List[Dict[str, Any]], session: Session
) -> Dict[str, int]:
    """Process search results and record as discovered issues."""
    stats = {"new": 0, "updated": 0, "duplicate": 0, "errors": 0, "rejected_non_periodical": 0}

    # ... existing code ...

    for result in search_results:
        try:
            # **NEW: Validate it's actually a periodical**
            if not self._validate_is_periodical(result):
                logger.info(f"Rejecting non-periodical result: {result.get('title')}")
                stats["rejected_non_periodical"] += 1
                continue

            # ... existing parsing code ...
```

#### B. Publisher/Source Validation

**Implementation Location:** `core/constants/publishers.py` (new file)

Create a database of known periodical publishers to increase confidence:

```python
"""Known periodical publishers and indicators."""

# Major periodical publishers (high confidence)
KNOWN_PERIODICAL_PUBLISHERS = {
    "condé nast",
    "hearst",
    "meredith",
    "time inc",
    "bauer media",
    "dennis publishing",
    "future plc",
    "penske media",
    "dotdash meredith",
    # Add more as discovered
}

# Publisher patterns in NZB metadata
PUBLISHER_PATTERNS = [
    r'\b(condé nast|hearst|meredith|time inc|bauer|dennis|future plc)\b',
]
```

**Usage in validation:**

```python
def _check_publisher(self, search_result: Dict[str, Any]) -> Optional[bool]:
    """
    Check if publisher is known periodical publisher.

    Returns:
        True: Known periodical publisher
        False: Known book publisher
        None: Unknown/ambiguous
    """
    from core.constants.publishers import KNOWN_PERIODICAL_PUBLISHERS, PUBLISHER_PATTERNS

    # Check description field if available
    description = search_result.get("description", "").lower()
    for publisher in KNOWN_PERIODICAL_PUBLISHERS:
        if publisher in description:
            return True

    return None  # Unknown
```

#### C. File Size Heuristics

**Implementation Location:** `services/issue_discovery.py`

Periodicals have typical file size ranges:

```python
def _validate_file_size(self, search_result: Dict[str, Any]) -> bool:
    """
    Validate file size is within typical periodical range.

    Typical ranges:
    - Magazines (PDF): 10MB - 500MB
    - Comics (CBZ/CBR): 50MB - 500MB
    - Books (EPUB): 1MB - 50MB (usually smaller)

    Returns:
        True if size is reasonable for periodical
    """
    size_bytes = search_result.get("size", 0)
    if size_bytes == 0:
        return True  # Unknown size, allow

    size_mb = size_bytes / (1024 * 1024)

    # Suspiciously small (likely book/article)
    if size_mb < 5:
        logger.warning(f"Suspicious: Very small file ({size_mb:.1f}MB), likely not a periodical")
        return False

    # Suspiciously large (likely collection/pack)
    if size_mb > 1000:
        logger.warning(f"Suspicious: Very large file ({size_mb:.1f}MB), likely a collection")
        return False

    return True
```

#### D. User Configuration

**Add to `config.template.yaml`:**

```yaml
tracking:
  validation:
    # Enable periodical validation to prevent downloading non-periodicals
    enable_periodical_validation: true

    # Strictness level: "strict", "moderate", "lenient"
    # strict: Reject anything without clear periodical indicators
    # moderate: Use heuristics and patterns (recommended)
    # lenient: Only reject obvious books/collections
    validation_strictness: 'moderate'

    # Manually whitelist/blacklist publishers
    publisher_whitelist: [] # e.g., ["Condé Nast", "Hearst"]
    publisher_blacklist: [] # e.g., ["Book Publisher Inc"]
```

---

## 2. Comprehensive NZB Name Parsing

### Problem

Current parsing at **Step 4a (Issue Discovery)** uses `core/parsers/metadata.py` which has limited pattern recognition. Real-world NZB names are highly variable:

**Examples of complex patterns:**

- `Wired.Magazine.USA.January.2024.True.PDF-PHOTOFILEv2`
- `National.Geographic-2024-01-HQ.PDF`
- `PC.Gamer.UK.Issue.389.February.2024.pdf`
- `The.Economist.2024.01.20.pdf`
- `TIME.V202.N25.2023.pdf` (Volume 202, Number 25)

### Current Limitations

From `core/parsers/metadata.py`:

- Basic regex patterns for dates
- Limited release group handling
- Doesn't extract country codes reliably
- Misses volume/issue numbers
- Poor handling of special characters and delimiters

### Proposed Solution

Enhance `core/parsers/metadata.py` with comprehensive pattern library:

#### A. Enhanced Pattern Recognition

**Implementation Location:** `core/parsers/metadata.py` - Add to `MetadataExtractor` class

```python
class MetadataExtractor:
    """Extract metadata from PDF filenames and directory structure."""

    def __init__(self):
        # ... existing code ...

        # Enhanced pattern library
        self.patterns = {
            # Date patterns (priority order - most specific first)
            "date_patterns": [
                # ISO format: 2024-01-20, 2024.01.20
                r'(?P<year>\d{4})[-./](?P<month>\d{1,2})[-./](?P<day>\d{1,2})',

                # Full month name: January 2024, Jan 2024
                r'(?P<month>january|february|march|april|may|june|july|august|september|october|november|december)[\s._-]+(?P<year>\d{4})',

                # Abbreviated month: Jan.2024, Jan-2024
                r'(?P<month>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\.?[\s._-]*(?P<year>\d{4})',

                # Numeric: 01-2024, 1/2024, 01.2024
                r'(?P<month>\d{1,2})[-./](?P<year>\d{4})',

                # Reversed: 2024-01, 2024.01
                r'(?P<year>\d{4})[-./](?P<month>\d{1,2})(?![-./]\d)',  # Negative lookahead to avoid full dates
            ],

            # Volume/Issue patterns
            "volume_patterns": [
                r'(?:vol\.?|volume|v)[\s._-]*(?P<volume>\d+)',
                r'\bv(?P<volume>\d+)\b',  # V12 (standalone)
            ],

            "issue_patterns": [
                r'(?:issue|no\.?|number|nr\.?|n)[\s._-]*(?P<issue>\d+)',
                r'#(?P<issue>\d+)',
                r'\b(?:i|n)(?P<issue>\d+)\b',  # I3, N3 (after volume)
            ],

            # Country/Region patterns
            "country_patterns": [
                r'\b(?P<country>USA?|UK|CA|AU|NZ|DE|FR|ES|IT|NL|SE|NO|DK|FI|JP|KR|CN|BR|MX|AR|IN)\b',
                r'\b(?P<country>United States|United Kingdom|Europe|Asia|North America)\b',
            ],

            # Language patterns
            "language_patterns": [
                r'\b(?P<language>English|German|French|Spanish|Italian|Portuguese|Russian|Japanese|Korean|Chinese)\b',
            ],

            # Edition/Variant patterns
            "edition_patterns": [
                r'\b(?P<edition>International|Global|European|Asian|Special|Limited|Digital|Print)\s+(?:Edition|Ed\.?)\b',
                r'\b(?:Edition|Ed\.?)[\s._-]*(?P<edition>International|Global|European|Asian|Special|Limited)\b',
            ],

            # Release group patterns (at end)
            "release_group_patterns": [
                r'-(?P<group>[A-Z0-9]+)$',  # -PHOTOFILEv2
                r'\[(?P<group>[A-Z0-9]+)\]$',  # [PHOTOFILE]
            ],

            # Quality indicators
            "quality_patterns": [
                r'\b(?P<quality>True\.?PDF|HQ|High\.?Quality|Retail|Original)\b',
            ],
        }

    def extract_from_filename(self, pdf_path: Path) -> Dict[str, Any]:
        """
        Extract comprehensive metadata from filename.

        Enhanced to handle complex NZB naming patterns.
        """
        filename = pdf_path.stem  # Without extension
        original_filename = filename

        metadata = {
            "title": None,
            "year": None,
            "month": None,
            "day": None,
            "volume": None,
            "issue": None,
            "country": None,
            "language": None,
            "edition": None,
            "release_group": None,
            "quality": None,
            "confidence": "low",
        }

        # Normalize delimiters: dots, underscores → spaces
        normalized = filename.replace(".", " ").replace("_", " ")

        # Extract components using pattern library
        remaining_text = normalized

        # 1. Extract release group (from end)
        for pattern in self.patterns["release_group_patterns"]:
            match = re.search(pattern, remaining_text, re.IGNORECASE)
            if match:
                metadata["release_group"] = match.group("group")
                # Remove from remaining text
                remaining_text = remaining_text[:match.start()].strip()
                break

        # 2. Extract quality indicators
        for pattern in self.patterns["quality_patterns"]:
            match = re.search(pattern, remaining_text, re.IGNORECASE)
            if match:
                metadata["quality"] = match.group("quality")
                # Remove from remaining text
                remaining_text = remaining_text[:match.start()] + remaining_text[match.end():]
                remaining_text = remaining_text.strip()

        # 3. Extract country/region
        for pattern in self.patterns["country_patterns"]:
            match = re.search(pattern, remaining_text, re.IGNORECASE)
            if match:
                metadata["country"] = match.group("country").upper()
                remaining_text = remaining_text[:match.start()] + remaining_text[match.end():]
                remaining_text = remaining_text.strip()
                break

        # 4. Extract language
        for pattern in self.patterns["language_patterns"]:
            match = re.search(pattern, remaining_text, re.IGNORECASE)
            if match:
                metadata["language"] = match.group("language").capitalize()
                remaining_text = remaining_text[:match.start()] + remaining_text[match.end():]
                remaining_text = remaining_text.strip()
                break

        # 5. Extract edition/variant
        for pattern in self.patterns["edition_patterns"]:
            match = re.search(pattern, remaining_text, re.IGNORECASE)
            if match:
                metadata["edition"] = match.group("edition").capitalize()
                remaining_text = remaining_text[:match.start()] + remaining_text[match.end():]
                remaining_text = remaining_text.strip()
                break

        # 6. Extract date (year, month, day)
        for pattern in self.patterns["date_patterns"]:
            match = re.search(pattern, remaining_text, re.IGNORECASE)
            if match:
                groups = match.groupdict()

                # Parse year
                if "year" in groups and groups["year"]:
                    year = int(groups["year"])
                    if MIN_VALID_YEAR <= year <= MAX_VALID_YEAR:
                        metadata["year"] = year

                # Parse month (name or number)
                if "month" in groups and groups["month"]:
                    month_str = groups["month"]
                    if month_str.isdigit():
                        month_num = int(month_str)
                        if 1 <= month_num <= 12:
                            metadata["month"] = month_num
                    else:
                        metadata["month"] = parse_month(month_str)

                # Parse day
                if "day" in groups and groups["day"]:
                    day = int(groups["day"])
                    if 1 <= day <= 31:
                        metadata["day"] = day

                # Remove from remaining text
                remaining_text = remaining_text[:match.start()] + remaining_text[match.end():]
                remaining_text = remaining_text.strip()
                break

        # 7. Extract volume
        for pattern in self.patterns["volume_patterns"]:
            match = re.search(pattern, remaining_text, re.IGNORECASE)
            if match:
                metadata["volume"] = int(match.group("volume"))
                remaining_text = remaining_text[:match.start()] + remaining_text[match.end():]
                remaining_text = remaining_text.strip()
                break

        # 8. Extract issue
        for pattern in self.patterns["issue_patterns"]:
            match = re.search(pattern, remaining_text, re.IGNORECASE)
            if match:
                metadata["issue"] = int(match.group("issue"))
                remaining_text = remaining_text[:match.start()] + remaining_text[match.end():]
                remaining_text = remaining_text.strip()
                break

        # 9. What remains is the title
        metadata["title"] = clean_title(remaining_text) if remaining_text else None

        # Calculate confidence score
        metadata["confidence"] = self._calculate_confidence(metadata)

        logger.debug(f"Extracted metadata from '{original_filename}': {metadata}")
        return metadata

    def _calculate_confidence(self, metadata: Dict[str, Any]) -> str:
        """
        Calculate confidence level based on extracted metadata.

        Returns: "high", "medium", or "low"
        """
        score = 0

        # Core components
        if metadata.get("title"):
            score += 2
        if metadata.get("year"):
            score += 2
        if metadata.get("month"):
            score += 2

        # Additional components
        if metadata.get("volume") or metadata.get("issue"):
            score += 1
        if metadata.get("country"):
            score += 1
        if metadata.get("quality"):
            score += 1

        if score >= 6:
            return "high"
        elif score >= 4:
            return "medium"
        else:
            return "low"
```

#### B. Pattern Testing Suite

**Add comprehensive tests:** `tests/unit/core/test_parser_metadata_enhanced.py`

```python
"""Tests for enhanced NZB name parsing."""

import pytest
from pathlib import Path
from core.parsers.metadata import MetadataExtractor


class TestEnhancedNZBParsing:
    """Test enhanced NZB filename parsing."""

    @pytest.fixture
    def extractor(self):
        return MetadataExtractor()

    def test_parse_complex_usa_magazine(self, extractor):
        """Test: Wired.Magazine.USA.January.2024.True.PDF-PHOTOFILEv2"""
        result = extractor.extract_from_filename(
            Path("Wired.Magazine.USA.January.2024.True.PDF-PHOTOFILEv2.pdf")
        )

        assert result["title"] == "Wired Magazine"
        assert result["country"] == "USA"
        assert result["year"] == 2024
        assert result["month"] == 1
        assert result["quality"] == "True PDF"
        assert result["release_group"] == "PHOTOFILEv2"
        assert result["confidence"] == "high"

    def test_parse_iso_date_format(self, extractor):
        """Test: National.Geographic-2024-01-HQ.PDF"""
        result = extractor.extract_from_filename(
            Path("National.Geographic-2024-01-HQ.PDF.pdf")
        )

        assert result["title"] == "National Geographic"
        assert result["year"] == 2024
        assert result["month"] == 1
        assert result["quality"] == "HQ"
        assert result["confidence"] == "high"

    def test_parse_volume_issue_format(self, extractor):
        """Test: TIME.V202.N25.2023.pdf"""
        result = extractor.extract_from_filename(
            Path("TIME.V202.N25.2023.pdf")
        )

        assert result["title"] == "TIME"
        assert result["volume"] == 202
        assert result["issue"] == 25
        assert result["year"] == 2023
        assert result["confidence"] == "high"

    def test_parse_uk_issue_format(self, extractor):
        """Test: PC.Gamer.UK.Issue.389.February.2024.pdf"""
        result = extractor.extract_from_filename(
            Path("PC.Gamer.UK.Issue.389.February.2024.pdf")
        )

        assert result["title"] == "PC Gamer"
        assert result["country"] == "UK"
        assert result["issue"] == 389
        assert result["month"] == 2
        assert result["year"] == 2024
        assert result["confidence"] == "high"

    def test_parse_weekly_date(self, extractor):
        """Test: The.Economist.2024.01.20.pdf"""
        result = extractor.extract_from_filename(
            Path("The.Economist.2024.01.20.pdf")
        )

        assert result["title"] == "The Economist"
        assert result["year"] == 2024
        assert result["month"] == 1
        assert result["day"] == 20
        assert result["confidence"] == "high"
```

---

## 3. Better Download/Organized Folder Organization

### Problem

Current organization at **Step 8d (File Import - Organize File)** uses a simple pattern:

```
{category}/{title}/{year}/
Example: _Magazines/Wired/2024/
```

**Limitations:**

- No separation of download vs. organized folders
- Limited customization
- Doesn't support multi-level categorization
- No publisher/imprint grouping
- Flat structure doesn't scale well

### Current Flow (from WORKFLOW.md)

```
Step 8d: File Import - Organize File
  → Build filename: "{title} - {month}{year}.{ext}"
  → Build directory: "{category}/{title}/{year}/"
  → Extract cover image
  → Move file and cover
```

### Proposed Solution

Implement a **Flexible Folder Structure System** with multiple organization patterns:

#### A. Separate Download and Organized Folders

**Implementation Location:** `services/file_organizer.py`

**Add clear separation:**

```python
class FileOrganizer:
    """Organize and rename files with flexible folder structures."""

    def __init__(
        self,
        downloads_dir: str,      # NEW: Explicit downloads directory
        organized_dir: str,      # NEW: Renamed from organize_dir
        category_prefix: str = "_",
        organization_pattern: str = "default",
    ):
        """
        Initialize file organizer with separate download/organized folders.

        Args:
            downloads_dir: Directory where download client saves files
            organized_dir: Base directory for organized library
            category_prefix: Prefix for category folders (e.g., "_")
            organization_pattern: Folder structure pattern to use
        """
        self.downloads_dir = Path(downloads_dir)
        self.organized_dir = Path(organized_dir)
        self.category_prefix = category_prefix
        self.organization_pattern = organization_pattern

        # Ensure directories exist
        self.downloads_dir.mkdir(parents=True, exist_ok=True)
        self.organized_dir.mkdir(parents=True, exist_ok=True)
```

**Benefits:**

- Downloads stay separate from organized library
- Can process files from downloads without mixing locations
- Easier to manage temporary files
- Clear "inbox" vs. "library" distinction

#### B. Multiple Organization Patterns

**Implementation Location:** `services/file_organizer.py`

**Add pattern registry:**

```python
class FileOrganizer:
    """Organize and rename files with flexible folder structures."""

    # Registry of organization patterns
    ORGANIZATION_PATTERNS = {
        # Pattern 1: Simple (current default)
        # {category}/{title}/{year}/
        # Example: _Magazines/Wired/2024/
        "simple": {
            "description": "Simple category > title > year structure",
            "template": "{category}/{title}/{year}",
            "supports": ["category", "title", "year"],
        },

        # Pattern 2: Publisher Grouped
        # {category}/{publisher}/{title}/{year}/
        # Example: _Magazines/Condé Nast/Wired/2024/
        "publisher": {
            "description": "Group by publisher for better organization",
            "template": "{category}/{publisher}/{title}/{year}",
            "supports": ["category", "publisher", "title", "year"],
        },

        # Pattern 3: Country/Language Grouped
        # {category}/{country}/{language}/{title}/{year}/
        # Example: _Magazines/USA/English/Wired/2024/
        "regional": {
            "description": "Group by country and language",
            "template": "{category}/{country}/{language}/{title}/{year}",
            "supports": ["category", "country", "language", "title", "year"],
        },

        # Pattern 4: Flat by Title
        # {category}/{title}/
        # Example: _Magazines/Wired/
        "flat": {
            "description": "Flat structure without year subdirectories",
            "template": "{category}/{title}",
            "supports": ["category", "title"],
        },

        # Pattern 5: Custom
        # User-defined pattern from config
        "custom": {
            "description": "Custom pattern from configuration",
            "template": None,  # Set from config
            "supports": None,  # Determined dynamically
        },
    }

    def _build_directory_path(
        self,
        category: str,
        title: str,
        metadata: Dict[str, Any],
    ) -> Path:
        """
        Build directory path based on organization pattern.

        Args:
            category: Periodical category (e.g., "Magazines", "Comics")
            title: Periodical title
            metadata: Dictionary with additional metadata (year, country, publisher, etc.)

        Returns:
            Full directory path
        """
        pattern_config = self.ORGANIZATION_PATTERNS.get(
            self.organization_pattern,
            self.ORGANIZATION_PATTERNS["simple"]
        )

        template = pattern_config["template"]
        if not template:
            # Custom pattern from config
            template = self.custom_pattern_template

        # Prepare substitution variables
        safe_category = f"{self.category_prefix}{sanitize_filename(category)}"
        safe_title = sanitize_filename(title)

        variables = {
            "category": safe_category,
            "title": safe_title,
            "year": metadata.get("year", "Unknown"),
            "country": metadata.get("country", "Unknown"),
            "language": metadata.get("language", "Unknown"),
            "publisher": sanitize_filename(metadata.get("publisher", "Unknown")),
        }

        # Format template
        try:
            relative_path = template.format(**variables)
        except KeyError as e:
            logger.warning(
                f"Template variable {e} not available, falling back to simple pattern"
            )
            # Fallback to simple pattern
            relative_path = f"{safe_category}/{safe_title}/{variables['year']}"

        return self.organized_dir / relative_path
```

#### C. Enhanced Filename Patterns

**Implementation Location:** `services/file_organizer.py`

**Add customizable filename patterns:**

```python
class FileOrganizer:
    """Organize and rename files with flexible naming."""

    # Registry of filename patterns
    FILENAME_PATTERNS = {
        # Pattern 1: Month-Year (current default)
        # Wired - December2024.pdf
        "month-year": {
            "description": "Title - MonthYear format",
            "template": "{title} - {month}{year}",
        },

        # Pattern 2: ISO Date
        # Wired - 2024-12.pdf
        "iso-date": {
            "description": "Title - YYYY-MM format",
            "template": "{title} - {year}-{month:02d}",
        },

        # Pattern 3: Issue Number
        # Wired - Issue 389.pdf
        "issue": {
            "description": "Title - Issue N format",
            "template": "{title} - Issue {issue}",
        },

        # Pattern 4: Volume + Issue
        # Wired - Vol 12 No 3.pdf
        "volume-issue": {
            "description": "Title - Vol X No Y format",
            "template": "{title} - Vol {volume} No {issue}",
        },

        # Pattern 5: Full Date (for weeklies)
        # The Economist - 2024-01-20.pdf
        "full-date": {
            "description": "Title - YYYY-MM-DD format",
            "template": "{title} - {year}-{month:02d}-{day:02d}",
        },

        # Pattern 6: Country + Date
        # PC Gamer UK - December2024.pdf
        "country-date": {
            "description": "Title [Country] - MonthYear format",
            "template": "{title} {country} - {month}{year}",
        },
    }

    def _build_filename(
        self,
        title: str,
        metadata: Dict[str, Any],
        extension: str,
    ) -> str:
        """
        Build filename based on configured pattern.

        Args:
            title: Periodical title
            metadata: Dictionary with date, issue, volume, etc.
            extension: File extension (.pdf, .epub, etc.)

        Returns:
            Formatted filename with extension
        """
        pattern_config = self.FILENAME_PATTERNS.get(
            self.filename_pattern,
            self.FILENAME_PATTERNS["month-year"]
        )

        template = pattern_config["template"]
        safe_title = sanitize_filename(title)

        # Prepare variables
        variables = {
            "title": safe_title,
            "year": metadata.get("year", "Unknown"),
            "month": metadata.get("month", 1),
            "day": metadata.get("day", 1),
            "issue": metadata.get("issue", ""),
            "volume": metadata.get("volume", ""),
            "country": metadata.get("country", ""),
        }

        # Convert month number to name if needed
        if "{month}" in template and isinstance(variables["month"], int):
            from core.constants.date import NUMBER_TO_MONTH
            variables["month"] = NUMBER_TO_MONTH.get(variables["month"], "Unknown")

        try:
            filename = template.format(**variables)
        except (KeyError, ValueError) as e:
            logger.warning(f"Filename template error: {e}, using fallback")
            # Fallback to simple pattern
            month_name = NUMBER_TO_MONTH.get(metadata.get("month", 1), "Unknown")
            filename = f"{safe_title} - {month_name}{metadata.get('year', 'Unknown')}"

        return f"{filename}{extension}"
```

#### D. Configuration Options

**Add to `config.template.yaml`:**

```yaml
organization:
  # Directory structure
  folders:
    # Separate downloads from organized library
    downloads_dir: 'local/downloads'
    organized_dir: 'local/organized'

    # Organization pattern: "simple", "publisher", "regional", "flat", "custom"
    pattern: 'simple'

    # Custom pattern (if pattern = "custom")
    # Available variables: {category}, {title}, {year}, {country}, {language}, {publisher}
    custom_pattern: '{category}/{publisher}/{title}/{year}'

    # Category prefix (e.g., "_" makes "_Magazines")
    category_prefix: '_'

  # Filename structure
  filenames:
    # Filename pattern: "month-year", "iso-date", "issue", "volume-issue", "full-date", "country-date"
    pattern: 'month-year'

    # Include volume/issue numbers in filename if available
    include_volume_issue: false

    # Include country code in filename if available
    include_country: false

  # Cover images
  covers:
    # Save cover images alongside PDFs
    extract_covers: true

    # Cover filename pattern: "same" (match PDF), "cover" (always "cover.jpg")
    cover_pattern: 'same'
```

#### E. Example Folder Structures

With these patterns, users can choose their preferred organization:

**Simple Pattern (Default):**

```
local/organized/
├── _Magazines/
│   ├── Wired/
│   │   ├── 2023/
│   │   │   ├── Wired - January2023.pdf
│   │   │   ├── Wired - February2023.pdf
│   │   ├── 2024/
│   │       ├── Wired - January2024.pdf
│   ├── National Geographic/
│       ├── 2024/
│           ├── National Geographic - January2024.pdf
```

**Publisher Pattern:**

```
local/organized/
├── _Magazines/
│   ├── Condé Nast/
│   │   ├── Wired/
│   │   │   ├── 2024/
│   │   │       ├── Wired - January2024.pdf
│   │   ├── The New Yorker/
│   │       ├── 2024/
│   │           ├── The New Yorker - 2024-01-20.pdf
│   ├── National Geographic Society/
│       ├── National Geographic/
│           ├── 2024/
│               ├── National Geographic - January2024.pdf
```

**Regional Pattern:**

```
local/organized/
├── _Magazines/
│   ├── USA/
│   │   ├── English/
│   │   │   ├── Wired/
│   │   │   │   ├── 2024/
│   │   │   │       ├── Wired - January2024.pdf
│   ├── UK/
│       ├── English/
│           ├── PC Gamer/
│               ├── 2024/
│                   ├── PC Gamer UK - January2024.pdf
```

**Flat Pattern:**

```
local/organized/
├── _Magazines/
│   ├── Wired/
│   │   ├── Wired - January2023.pdf
│   │   ├── Wired - February2023.pdf
│   │   ├── Wired - January2024.pdf
│   ├── National Geographic/
│       ├── National Geographic - January2024.pdf
│       ├── National Geographic - February2024.pdf
```

---

## Implementation Priority

### Phase 1: Critical (Prevent Bad Downloads)

1. **Non-Periodical Validation** - Implement `_validate_is_periodical()` in `services/issue_discovery.py`
2. **Basic Pattern Library** - Add core date/issue patterns to `core/parsers/metadata.py`

### Phase 2: Enhancement (Better Parsing)

3. **Enhanced NZB Parsing** - Complete pattern library in `MetadataExtractor`
4. **Comprehensive Tests** - Add test suite for all NZB patterns

### Phase 3: Organization (Better Structure)

5. **Separate Folders** - Implement downloads vs. organized distinction
6. **Pattern Registry** - Add organization pattern system
7. **Configuration** - Update `config.template.yaml` with new options

---

## Testing Strategy

### Unit Tests

**Test Coverage:**

- `tests/unit/core/test_parser_metadata_enhanced.py` - NZB parsing patterns
- `tests/unit/services/test_issue_discovery_validation.py` - Periodical validation
- `tests/unit/services/test_file_organizer_patterns.py` - Folder patterns

### Integration Tests

**Test Coverage:**

- End-to-end: Search → Validate → Download → Organize
- Pattern switching
- Fallback behavior

### Real-World Test Data

**Create test dataset:** `tests/fixtures/nzb_samples/`

```
nzb_samples/
├── magazines/
│   ├── wired_usa_jan2024.nzb
│   ├── national_geographic_iso_date.nzb
│   ├── pc_gamer_uk_issue.nzb
├── books/ (should be rejected)
│   ├── complete_collection.nzb
│   ├── anthology.nzb
```

---

## Migration Path

For existing installations:

1. **Backward Compatible:** Default patterns match current behavior
2. **Opt-in Enhancement:** Enable new features via config
3. **Reorganization Tool:** Provide script to reorganize existing library

**Script:** `scripts/reorganize_library.py`

```python
"""
Reorganize existing library with new folder patterns.

Usage:
    .venv/bin/python scripts/reorganize_library.py --pattern publisher --dry-run
    .venv/bin/python scripts/reorganize_library.py --pattern regional
"""
```

---

## Summary

These improvements address the three key areas:

1. **Non-Periodical Prevention:** Multi-layer validation (category, patterns, publisher, size)
2. **Comprehensive Parsing:** Enhanced pattern library for complex NZB names
3. **Better Organization:** Flexible folder structures with multiple patterns

**Expected Benefits:**

- Fewer false positives (books, collections misidentified as periodicals)
- Higher metadata extraction accuracy (90%+ from filenames alone)
- Scalable organization for large libraries (1000+ periodicals)
- User choice in organization preferences

---

**Last Updated:** January 20, 2026
