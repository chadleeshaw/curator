# Curator Terminology Guide

This document defines the core concepts and terminology used throughout Curator's codebase.

## Overview

The magazine/periodical publishing domain has **overloaded terminology** where words like "edition" have multiple conflicting meanings. This guide establishes clear, consistent definitions to avoid confusion in code, documentation, and UI.

---

## Core Concepts

### 1. Periodical

**Definition**: A publication series released on a regular schedule (weekly, monthly, quarterly, etc.).

**Examples**:
- "Wired"
- "National Geographic"
- "PC Gamer"
- "The New York Times Magazine"

**In Code**:
- Database model: `Periodical` (represents a single downloaded issue file)
- Database model: `PeriodicalTracking` (represents tracking configuration for a periodical series)

---

### 2. Regional Periodical

**Definition**: A country-specific version of a periodical with separate editorial teams, content, and identity. These are **DIFFERENT periodicals**, not just translations.

**Examples**:
- "Wired UK" ≠ "Wired US" (different editorial teams)
- "Vogue France" ≠ "Vogue US" (different content)
- "National Geographic Australia" ≠ "National Geographic" (different publication)

**In Code**:
```python
# Identified by REGIONAL_PERIODICAL_INDICATORS
# Current: REGIONAL_EDITION_INDICATORS (to be renamed)
"uk", "us", "france", "germany", "australia"
```

**Database**:
```python
country = Column(String(50), nullable=True, index=True)  
# Country/region of periodical (e.g., "US", "UK", "AU")
```

---

### 3. Audience Periodical

**Definition**: A demographic-specific version of a periodical targeting a different audience. These are **DIFFERENT periodicals** with distinct content and editorial direction.

**Examples**:
- "National Geographic" ≠ "National Geographic Kids" (different audience)
- "PC Gamer" ≠ "PC Gamer Pro" (different content)
- "Time" ≠ "Time Traveller" (different publication)

**In Code**:
```python
# Identified by AUDIENCE_PERIODICAL_INDICATORS  
# Current: EDITION_VARIANT_INDICATORS (to be renamed)
"kids", "little kids", "pro", "professional", "traveller"
```

---

### 4. Issue / Edition Number

**Definition**: An individual numbered release of a periodical series. This is the publishing industry's primary use of the word "edition."

**Examples**:
- "Wired Edition 123"
- "National Geographic Issue 45"
- "PC Gamer Vol 5 No 3"
- "January 2024 issue"

**Important**: When the publishing industry says "latest edition," they mean "latest issue" (numbered release), NOT regional variant.

**In Code**:
```python
issue_number = Column(String(50), nullable=True)  # "123", "45", "Vol 5 No 3"
issue_date = Column(DateTime(timezone=True), nullable=False)  # Publication date
```

---

### 5. Special Issue

**Definition**: A themed or special release of the **SAME** periodical, not a different publication. Often uses the word "edition" in its title.

**Examples**:
- "Wired Summer Edition" (same periodical, seasonal theme)
- "Time Person of the Year" (same periodical, annual special)
- "National Geographic Collector's Edition" (same periodical, special release)
- "Sports Illustrated Swimsuit Edition" (same periodical, annual theme)

**Distinguishing Feature**: These are **part of the same periodical series**, just with special themes or timing.

**In Code**:
```python
# Database fields
is_special_edition = Column(Boolean, default=False)
special_edition_name = Column(String(255), nullable=True)  # "Summer Edition", "Person of the Year"

# Detection function
def is_special_issue(title: str) -> bool:
    """Check if title indicates a special issue (not a regional/audience periodical)"""
```

---

### 6. Download Variant

**Definition**: The **exact same issue file** available from multiple download sources. These are deduplication targets - we only want to download it once, but track all sources.

**Examples**:
- "Wired Jan 2024.pdf" from provider A (hash: abc123)
- "Wired - January 2024.pdf" from provider B (hash: abc123)  
  → Same file, different filenames, multiple sources

**Distinguishing Features**:
- Same or very similar title (fuzzy match)
- Same publication date
- Same or similar file size
- Potentially same content hash

**In Code**:
```python
# DiscoveredIssue tracks multiple sources for the same issue
search_result_ids = Column(JSON, default=list)  # List of SearchResult.id we've seen
submission_ids = Column(JSON, default=list)     # List of download attempts

# Deduplication
fuzzy_match_group = Column(String(255), nullable=False, index=True)
```

**In UI**:
```javascript
// Badge showing multiple download sources
📥 3 variants  // Same issue available from 3 providers
```

---

## Terminology Summary Table

| Term | What It Is | Relationship | Code Concept |
|------|-----------|--------------|--------------|
| **Periodical** | Publication series | Base concept | "Wired", "National Geographic" |
| **Regional Periodical** | Country-specific version | **Different periodical** | "Wired UK" ≠ "Wired US" |
| **Audience Periodical** | Demographic-specific version | **Different periodical** | "Nat Geo" ≠ "Nat Geo Kids" |
| **Issue / Edition Number** | Individual numbered release | **Part of same periodical** | "Issue 123", "January 2024" |
| **Special Issue** | Themed release | **Part of same periodical** | "Summer Edition", "Person of the Year" |
| **Download Variant** | Same file from multiple sources | **Exact duplicate** | Multiple NZBs for same issue |

---

## Common Confusions

### "Edition" is Overloaded! 

The word "edition" has **THREE different meanings** in the periodical domain:

1. **Regional Edition** (e.g., "UK edition of Wired")
   - Different periodical
   - Separate editorial team
   - Different content

2. **Issue/Edition Number** (e.g., "Edition 123", "latest edition")
   - Individual release
   - **Most common publishing industry usage**
   - Part of same periodical

3. **Special Edition** (e.g., "Summer Edition")
   - Themed issue
   - Part of same periodical
   - Often annual or seasonal

**In Curator**: We avoid using "edition" alone. Instead:
- "Regional periodical" for country variants
- "Issue number" for numbered releases  
- "Special issue" for themed releases

---

## Code Terminology Standards

### Current State (This Branch)

The filter fix correctly handles the concepts but uses legacy terminology:

```python
# Functions (current names)
def extract_edition_variant(title) -> Optional[str]:
    """Extracts regional/audience indicators: 'uk', 'kids', 'pro'"""

def filter_edition_variants(results, query):
    """Filters out different regional/audience periodicals"""

# Constants (current names)  
REGIONAL_EDITION_INDICATORS = {"uk", "us", "france", ...}
EDITION_VARIANT_INDICATORS = {"kids", "pro", "traveller", ...}
```

### Recommended Naming (Future Refactor)

For clarity, these should eventually be renamed to use "periodical" terminology:

```python
# Functions (proposed names)
def extract_periodical_variant(title) -> Optional[str]:
    """Extracts regional/audience indicators that distinguish different periodicals"""

def filter_periodical_variants(results, query):
    """Filters out different regional/audience periodicals"""

# Constants (proposed names)
REGIONAL_PERIODICAL_INDICATORS = {"uk", "us", "france", ...}
AUDIENCE_PERIODICAL_INDICATORS = {"kids", "pro", "traveller", ...}
```

---

## Usage Examples

### Example 1: Regional Periodicals

```python
# These are DIFFERENT periodicals (separate tracking)
tracking_uk = PeriodicalTracking(
    title="Wired UK",
    country="UK",
    language="English"
)

tracking_us = PeriodicalTracking(
    title="Wired US", 
    country="US",
    language="English"
)

# Search filtering
search("Wired UK")
# ✅ Keeps: "Wired UK Issue 45", "Wired - December 2024" (same periodical)
# ❌ Filters: "Wired US Issue 45" (different periodical)
```

### Example 2: Audience Periodicals

```python
# These are DIFFERENT periodicals (separate tracking)
tracking_base = PeriodicalTracking(
    title="National Geographic",
    language="English"
)

tracking_kids = PeriodicalTracking(
    title="National Geographic Kids",
    language="English"
)

# Search filtering
search("National Geographic")
# ✅ Keeps: "National Geographic December 2024"
# ❌ Filters: "National Geographic Kids December 2024" (different periodical)
```

### Example 3: Special Issues

```python
# Special issues are PART OF the same periodical
periodical = Periodical(
    title="Time",
    issue_date=datetime(2024, 12, 1),
    derived_metadata={
        "is_special_edition": {"value": True, "source": "file_scan"},
        "special_edition_name": {"value": "Person of the Year", "source": "file_scan"}
    }
)

# This is still tracked under the base "Time" tracking record
# Not a separate periodical!
```

### Example 4: Download Variants

```python
# Same issue discovered from multiple providers
discovered_issue = DiscoveredIssue(
    tracking_id=123,
    title="Wired - January 2024",
    fuzzy_match_group="wired_2024_01",
    search_result_ids=[456, 789, 1011],  # 3 different search results
    latest_url="http://provider3.com/wired-jan-2024.nzb",
    latest_provider="provider3"
)

# UI shows: "📥 3 variants" (same issue, 3 download sources)
# We only download it once, but user can choose which source
```

---

## Filter Logic Explained

### Regional Periodical Filtering

When searching for "Wired UK":

1. **Query variant**: "uk" (regional indicator)
2. **Results**:
   - "Wired UK Issue 45" → variant="uk" → ✅ **KEEP** (exact match)
   - "Wired Issue 45" → variant=None → ✅ **KEEP** (alias without region)
   - "Wired US Issue 45" → variant="us" → ❌ **FILTER** (different periodical)

**Rationale**: Providers often index "Wired UK" as just "Wired", so we must keep results without regional suffix to avoid missing valid issues found via aliases.

### Audience Periodical Filtering

When searching for "National Geographic":

1. **Query variant**: None
2. **Results**:
   - "National Geographic Dec 2024" → variant=None → ✅ **KEEP** (exact match)
   - "National Geographic Kids Dec 2024" → variant="kids" → ❌ **FILTER** (different periodical)
   - "Nat Geo Traveller Dec 2024" → variant="traveller" → ❌ **FILTER** (different periodical)

**Rationale**: Audience variants (Kids, Pro, Traveller) are always explicit - they won't be indexed without the suffix, so strict filtering is safe.

---

## Database Schema

### Periodical (Downloaded Issue File)

```python
class Periodical(Base):
    """A single downloaded issue file"""
    
    title = Column(String(255))           # Periodical series name
    language = Column(String(50))         # Language of the periodical
    issue_date = Column(DateTime)         # Publication date of this issue
    
    # Special issue metadata
    derived_metadata = Column(JSON)       # Contains is_special_edition, special_edition_name
```

### PeriodicalTracking (Tracking Configuration)

```python
class PeriodicalTracking(Base):
    """Tracking configuration for a periodical series"""
    
    title = Column(String(255))           # Periodical name (may include regional/audience indicator)
    language = Column(String(50))         # Language of tracked periodical
    country = Column(String(50))          # Country/region of periodical (for regional variants)
```

### DiscoveredIssue (Available Issues with Download Variants)

```python
class DiscoveredIssue(Base):
    """Persistent tracking of discovered issues from search results"""
    
    tracking_id = Column(Integer)         # Links to PeriodicalTracking
    title = Column(String(255))           # Original title from search
    fuzzy_match_group = Column(String)    # For deduplication
    
    # Download variant tracking
    search_result_ids = Column(JSON)      # List of SearchResult IDs (multiple sources)
    submission_ids = Column(JSON)         # List of download attempt IDs
    latest_url = Column(String)           # Most recent download URL
    latest_provider = Column(String)      # Most recent provider
```

---

## UI Terminology

### Search Results

- **"3 variants"** badge → Same issue available from 3 different providers (download variants)
- **Language filter: "English"** → Filters to English-language periodicals
- **Country filter: "UK"** → Filters to UK regional periodicals

### Tracking Page

- **"Wired UK"** → Regional periodical (separate from "Wired US")
- **"National Geographic Kids"** → Audience periodical (separate from base "National Geographic")
- **Issue list** → Individual numbered releases (issues)

### Periodical Detail Page

- **"⭐ Special Edition"** badge → Marks this issue as a special/themed release
- **"Special Edition Name"** field → "Summer Edition", "Person of the Year", etc.

---

## Test Terminology

From `tests/unit/web/routers/test_filter_edition_variants.py`:

```python
"""
Key terminology:
- "Editions" = individual issue numbers/volumes (Issue 1, Issue 2, Vol 3, etc.)
- "Variants" = the same issue available from multiple providers (deduplication targets)
- "Publication variants" = geographically/demographically distinct publications
  (e.g. "Wired UK" vs "Wired US", "National Geographic" vs "National Geographic Kids")
"""
```

**Note**: Tests use "publication variants" - should eventually be "periodical variants" for consistency.

---

## Future Refactoring Plan

### Phase 1: Documentation (Non-Breaking) ✅
- [x] Create `docs/TERMINOLOGY.md` (this file)
- [ ] Update docstrings to use "periodical" terminology
- [ ] Update database column comments
- [ ] Add terminology guide to README

### Phase 2: Function Renames (Breaking Changes)
- [ ] `extract_edition_variant()` → `extract_periodical_variant()`
- [ ] `filter_edition_variants()` → `filter_periodical_variants()`
- [ ] `get_periodical_editions()` → `get_periodical_issues()`

### Phase 3: Constant Reorganization
- [ ] Rename `core/constants/edition.py` → `core/constants/periodical.py`
- [ ] `REGIONAL_EDITION_INDICATORS` → `REGIONAL_PERIODICAL_INDICATORS`
- [ ] `EDITION_VARIANT_INDICATORS` → `AUDIENCE_PERIODICAL_INDICATORS`

### Phase 4: UI/API Documentation
- [ ] Update OpenAPI endpoint descriptions
- [ ] Update UI tooltips and help text
- [ ] Add glossary section to user documentation

---

## References

- **Filter fix commit**: `f2585ad` - Correctly handles regional periodical filtering
- **Test documentation**: `tests/unit/web/routers/test_filter_edition_variants.py`
- **Constants**: `core/constants/edition.py`
- **Parser logic**: `core/parsers/title.py`

---

**Last Updated**: 2026-02-18  
**Branch**: `claude/fix-editions-variants-search-kvNtT`
