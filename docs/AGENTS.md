# Curator - Developer Guide

This guide provides essential information for developers and AI coding agents working in the Curator codebase.

## Project Overview

Curator is a modular system for discovering, downloading, and organizing periodicals (magazines, comics, newspapers) using Newsnab APIs and download clients. Built with Python 3.13 + FastAPI backend and vanilla JavaScript ES6 frontend.

---

## 🚨 Critical Rules

### Python Environment

**ALWAYS use `.venv/bin/python`** - Never use bare `python` or `pytest`:

```bash
# Correct ✅
.venv/bin/python -m pytest tests/
.venv/bin/python main.py
.venv/bin/python -m black <files>

# Wrong ❌
python main.py
pytest tests/
```

### Pre-Push Validation

**ALWAYS run `make ci-lint` before committing** - This matches GitHub CI exactly:

```bash
make ci-lint    # Must pass before push
```

The project includes a pre-push hook that automatically runs `make ci-lint`. Install it with:

```bash
make install-hooks
# or
./setup-hooks.sh
```

### Constants Location

**NEVER define constants in utility modules** - All constants go in `core/constants/`:

```python
# Wrong ❌
# core/parsers/date.py
MONTH_MAP = {"jan": 1}

# Correct ✅
# core/constants/date.py
MONTH_TO_NUMBER = {"jan": 1, "january": 1, ...}

# core/parsers/date.py
from core.constants.date import MONTH_TO_NUMBER
```

---

## Essential Commands

### Development

```bash
make run                    # Start application
make install                # Install dependencies
make install-hooks          # Install git pre-push hooks
```

### Testing

```bash
# Run all tests
.venv/bin/python -m pytest tests/ -v --tb=short

# Run specific tests
.venv/bin/python -m pytest tests/unit/ -v                      # Unit tests only
.venv/bin/python -m pytest tests/unit/core/parsers/ -v         # Parser tests
.venv/bin/python -m pytest tests/test_file.py -v               # Single file
.venv/bin/python -m pytest tests/test_file.py::test_func -v    # Single test

# Quick test categories
make test-routers           # Router/API tests only
make test-quick             # Syntax check only
```

### Linting & Formatting

```bash
# CI linting (matches GitHub Actions - run before pushing!)
make ci-lint                # Fails on any errors (recommended)

# Auto-format code
make format                 # All languages
make format-python          # Black
make format-js              # Prettier
make format-css             # Prettier

# Individual linters
make lint                   # All linters (suppresses errors)
make lint-python            # pylint + flake8
make lint-js                # ESLint
make lint-css               # Stylelint
```

---

## Project Structure

```
curator/
├── main.py              # Application entry point
├── core/                # Core utilities
│   ├── config.py        # Configuration loader
│   ├── database.py      # Database connection
│   ├── auth.py          # Authentication
│   ├── constants/       # ALL constants defined here
│   │   ├── date.py      # Date/month mappings
│   │   ├── files.py     # File extensions, MIME types
│   │   ├── language.py  # Language codes
│   │   ├── country.py   # Country codes
│   │   └── ...
│   ├── parsers/         # Parsing utilities
│   └── utils/           # Utility functions
├── models/              # SQLAlchemy database models
│   ├── database.py      # Model definitions
│   └── migrations/      # Schema migrations
├── providers/           # Search providers
│   ├── newsnab.py       # Newsnab API provider
│   └── rss.py           # RSS feed provider
├── clients/             # Download clients
│   ├── sabnzbd.py       # SABnzbd client
│   └── nzbget.py        # NZBGet client
├── services/            # Business logic
│   ├── file_organizer/  # File organization
│   ├── importer/        # File import
│   ├── ocr/             # OCR processing
│   └── ...
├── schedulers/          # Background tasks
│   ├── scheduler.py
│   ├── download_monitor.py
│   └── ocr_processor.py
├── web/                 # FastAPI application
│   ├── app.py           # Main FastAPI app
│   ├── schemas.py       # Pydantic schemas
│   ├── routers/         # API endpoints
│   │   ├── periodicals/ # Periodical management
│   │   ├── tracking/    # Tracking management
│   │   ├── downloads/   # Download management
│   │   └── search/      # Search endpoints
│   └── middleware/
├── static/              # Frontend assets
│   ├── js/
│   │   ├── core/        # API client, auth, errors, utils
│   │   ├── features/    # Library, tracking, downloads
│   │   └── readers/     # PDF, EPUB, comic readers
│   └── css/
├── templates/           # HTML templates
└── tests/               # Test suite
    ├── unit/
    ├── integration/
    └── e2e/
```

---

## Code Style Guidelines

### Python

#### Formatting

- **Line length**: 120 characters maximum
- **Indentation**: 4 spaces (no tabs)
- **Formatter**: Black (`make format-python`)
- **Type hints**: Required for all function parameters and return values

#### Imports

Order matters - separate groups with blank lines:

```python
import logging                          # 1. Standard library
from pathlib import Path
from typing import Dict, Optional

from fastapi import APIRouter           # 2. Third-party
from sqlalchemy import Column

from core.constants import DEFAULT_VAL  # 3. Local imports
from core.config import ConfigLoader
```

#### Constants

Constants are organized by domain in `core/constants/`:

```python
# core/constants/date.py
MONTH_TO_NUMBER = {
    "jan": 1,
    "january": 1,
    # ...
}
"""Month name/abbreviation to number mapping (case-insensitive)"""

MIN_VALID_YEAR = 1900
"""Minimum valid year for publication dates"""

UNKNOWN_ISSUE_DATE_YEAR = 1900
"""Sentinel year for periodicals without detectable dates"""
```

When adding new constants:
1. Find appropriate file in `core/constants/` by domain
2. Add constant with descriptive docstring
3. Export from `core/constants/__init__.py` if widely used
4. Import in modules that need it

#### Error Handling

```python
# ✅ CORRECT - Using the exception variable
try:
    result = process()
except ValueError as e:
    logger.error(f"Failed: {e}")
    raise

# ✅ CORRECT - Not using exception, so don't capture it
try:
    result = process()
except ValueError:
    return None

# ❌ WRONG - Capturing but not using exception
try:
    result = process()
except ValueError as e:  # 'e' is never used!
    return None
```

#### Logging

```python
import logging
logger = logging.getLogger(__name__)

logger.debug("Detailed diagnostic info")
logger.info("General informational message")
logger.warning("Warning about potential issue")
logger.error("Error occurred", exc_info=True)
```

#### Code Cleanliness

**No unused code:**
- No unused imports
- No unused variables
- No unused functions
- Run `autoflake` to detect and remove unused code:

```bash
# Check for unused code
.venv/bin/python -m autoflake --check --remove-all-unused-imports --remove-unused-variables <file>

# Auto-fix unused code
.venv/bin/python -m autoflake --in-place --remove-all-unused-imports --remove-unused-variables <file>
```

### JavaScript

#### Module System

Use ES6 modules with organized subdirectories:

```javascript
// core/errors.js
export class APIError extends Error { ... }

// core/api.js
import { AuthManager } from './auth.js';
import { APIError } from './errors.js';

export class APIClient { ... }

// features/library.js
import { APIClient } from '../core/api.js';
import { UIUtils } from '../core/ui-utils.js';
```

#### Formatting

- **Line length**: 100 characters
- **Indentation**: 2 spaces
- **Quotes**: Single quotes
- **Semicolons**: Required
- **Formatter**: Prettier

#### User Confirmation Dialogs

**NEVER use JavaScript `confirm()`, `alert()`, or `prompt()`** - Use modal dialogs instead:

```javascript
// ❌ WRONG - Do not use confirm()
if (!confirm('Are you sure?')) {
  return;
}

// ✅ CORRECT - Use modal dialogs
openConfirmationModal() {
  UIUtils.showModal('my-confirmation-modal');
}

closeConfirmationModal() {
  UIUtils.closeModal('my-confirmation-modal');
}

async confirmAction() {
  this.closeConfirmationModal();
  // Perform the action
}
```

---

## Testing Guidelines

### Test Structure

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.parsers.metadata import FilenameParser

class TestFilenameParser:
    def test_parse_month_year(self):
        """Test parsing month and year from filename"""
        parser = FilenameParser()
        result = parser.extract_from_nzb_title("Magazine - Jan2024")
        
        assert result["month"] == 1
        assert result["year"] == 2024
```

### Running Tests

```bash
# Specific file
.venv/bin/python -m pytest tests/unit/core/test_parser.py -v

# Specific test class
.venv/bin/python -m pytest tests/test_file.py::TestClassName -v

# Specific test function
.venv/bin/python -m pytest tests/test_file.py::test_function -v

# With debugging output
.venv/bin/python -m pytest tests/test_file.py -vv -s
```

---

## Common Tasks

### Adding an API Endpoint

1. Create/modify router in `web/routers/<domain>/`
2. Add Pydantic schema to `web/schemas.py` if needed
3. Add tests in `tests/unit/web/routers/`
4. Document with docstrings

```python
# web/routers/example.py
router = APIRouter(prefix="/api", tags=["example"])

@router.get("/items")
async def list_items(skip: int = 0, limit: int = 50) -> Dict[str, Any]:
    """List items with pagination."""
    ...
```

### Adding a Service

1. Create `services/<name>/`
2. Export from `services/__init__.py`
3. Add tests in `tests/unit/services/`
4. Integrate in `web/app.py` lifespan if needed

### Adding Constants

1. Determine appropriate file in `core/constants/` by domain
2. Add constant with docstring
3. Export from `core/constants/__init__.py` if widely used
4. Import in modules that need it

```python
# core/constants/date.py
UNKNOWN_ISSUE_DATE_YEAR = 1900
"""Sentinel year for periodicals without detectable dates"""

# core/constants/__init__.py
from .date import UNKNOWN_ISSUE_DATE_YEAR

__all__ = [
    "UNKNOWN_ISSUE_DATE_YEAR",
    # ...
]
```

---

## Configuration

### Config Files

- `config.template.yaml` - Template with all options documented
- `local/config/config.yaml` - Active config (gitignored)
- `tests/config.test.yaml` - Test config

### Environment Variables

- `CURATOR_CONFIG_PATH` - Custom config file location
- `CURATOR_DRY_RUN` - Enable dry run mode (`true`/`false`)
- `DISABLE_OCR` - Disable OCR features (`true`/`false`)
- `CURATOR_LOG_LEVEL` - Log level (DEBUG, INFO, WARNING, ERROR)
- `USE_GPU` - GPU mode for OCR (`0` for CPU-only)

### Config Synchronization

The application automatically synchronizes user configuration with `config.template.yaml` on startup:
- User values are preserved
- New options added with defaults
- Deprecated keys removed
- Automatic backups created (`.bak` files)

See `core/config_merge.py` for implementation details.

---

## Key Concepts

### Terminology

Curator uses specific terminology to avoid confusion in the periodical domain:

- **Periodical**: Publication series (e.g., "Wired", "National Geographic")
- **Regional Periodical**: Country-specific version (e.g., "Wired UK" ≠ "Wired US")
- **Audience Periodical**: Demographic version (e.g., "Nat Geo" ≠ "Nat Geo Kids")
- **Issue**: Individual numbered release (e.g., "Issue 123", "January 2024")
- **Special Issue**: Themed release (e.g., "Summer Edition")
- **Download Variant**: Same file from multiple sources

See `docs/TERMINOLOGY.md` for complete definitions and examples.

### Date Handling

- **Sentinel dates**: Periodicals without detectable dates use `1900-01-01` instead of current date
- **Issue dates**: Use `issue_date` column (DateTime with timezone)
- **Unknown dates**: Constant `UNKNOWN_ISSUE_DATE_YEAR = 1900` in `core/constants/date.py`

---

## Dependencies

- Python 3.13+ required
- FastAPI 0.104.1, SQLAlchemy 2.0.45, uvicorn
- pytest 8.0+, Black 24.0+, pylint, flake8
- Node.js (ESLint, Prettier, Stylelint)

## Installation

```bash
# Install all dependencies
make install

# Or manually
pip install -r requirements.txt
npm install
```

---

## File References

When referencing code locations, use `file_path:line_number` format:

```
The validation logic is in services/file_organizer/core.py:459
```

---

**Remember**: 
- Always use `.venv/bin/python` for Python commands
- Run `make ci-lint` before committing
- Keep code clean - no unused imports/variables
- Use modal dialogs, not `confirm()`
