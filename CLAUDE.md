# Curator - Claude Development Guide

Curator is a Python 3.13 + FastAPI application for discovering, downloading, and organizing periodicals (magazines, comics, newspapers) with a vanilla JavaScript ES6 frontend.

## Critical Rules

### Python Environment
**ALWAYS use `.venv/bin/python`** - Never use bare `python` or `pytest`:
```bash
# Correct
.venv/bin/python -m pytest tests/
.venv/bin/python main.py

# Wrong
python main.py
pytest tests/
```

### Pre-Push Validation
**ALWAYS run `make ci-lint` before committing** - This matches GitHub CI exactly:
```bash
make ci-lint    # Must pass before push
```

### Constants Location
**NEVER define constants in utility modules** - All constants go in `core/constants/`:
```python
# Wrong - in core/parsers/date.py
MONTH_MAP = {"jan": 1}

# Correct - import from constants
from core.constants.date import MONTH_TO_NUMBER
```

## Essential Commands

```bash
# Development
make run                    # Start application
make install                # Install dependencies
make install-hooks          # Install git pre-push hooks

# Testing
.venv/bin/python -m pytest tests/ -v --tb=short           # All tests
.venv/bin/python -m pytest tests/unit/ -v                 # Unit tests only
.venv/bin/python -m pytest tests/path/test_file.py -v     # Single file
.venv/bin/python -m pytest tests/test_file.py::test_func  # Single test

# Linting & Formatting
make ci-lint               # CI linters (run before push!)
make format                # Auto-format all code
make lint                  # Run all linters

# Individual tools
.venv/bin/python -m black --line-length=120 <files>
.venv/bin/python -m flake8 <files>
.venv/bin/python -m pylint --fail-under=7.0 <files>
npx eslint static/js/*.js
npx prettier --write <files>
```

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
│   ├── file_organizer.py
│   ├── download_manager.py
│   ├── cache.py
│   └── ocr/             # OCR processing
├── schedulers/          # Background tasks
│   ├── scheduler.py
│   ├── download_monitor.py
│   └── ocr_processor.py
├── web/                 # FastAPI application
│   ├── app.py           # Main FastAPI app
│   ├── schemas.py       # Pydantic schemas
│   ├── routers/         # API endpoints
│   │   ├── auth.py
│   │   ├── config.py
│   │   ├── periodicals/ # Periodical management
│   │   ├── tracking/    # Tracking management
│   │   ├── downloads/   # Download management
│   │   └── search/      # Search endpoints
│   └── middleware/
├── static/              # Frontend assets
│   ├── js/
│   │   ├── core/        # API client, auth, errors, utils
│   │   ├── features/    # Library, tracking, downloads, etc.
│   │   └── readers/     # PDF, EPUB, comic readers
│   └── css/
├── templates/           # HTML templates
└── tests/               # Test suite
    ├── unit/
    ├── integration/
    ├── e2e/
    └── fixtures/
```

## Code Style

### Python

**Formatting:**
- Line length: 120 characters
- Indentation: 4 spaces
- Formatter: Black (`make format-python`)

**Imports** (order matters):
```python
import logging                          # 1. Standard library
from pathlib import Path
from typing import Dict, Optional

from fastapi import APIRouter           # 2. Third-party
from sqlalchemy import Column

from core.constants import DEFAULT_VAL  # 3. Local imports
from core.config import ConfigLoader
```

**Type hints required:**
```python
def parse_date(date_str: str) -> Optional[datetime]:
    """Parse date string to datetime."""
    ...
```

**Error handling:**
```python
# If using exception variable, use it
try:
    result = process()
except ValueError as e:
    logger.error(f"Failed: {e}")  # 'e' is used
    raise

# If not using exception variable, don't capture it
try:
    result = process()
except ValueError:
    return None  # No 'as e' needed
```

**Logging:**
```python
import logging
logger = logging.getLogger(__name__)

logger.debug("Detailed info")
logger.info("General info")
logger.warning("Warning")
logger.error("Error occurred", exc_info=True)
```

### JavaScript

**Module system:** ES6 imports/exports
```javascript
import { APIClient } from '../core/api.js';
import { UIUtils } from '../core/ui-utils.js';

export class FeatureManager { ... }
```

**Formatting:**
- Line length: 100 characters
- Indentation: 2 spaces
- Quotes: Single quotes
- Semicolons: Required

**No native dialogs** - Use modal components instead:
```javascript
// Wrong
if (!confirm('Are you sure?')) return;

// Correct
UIUtils.showModal('confirmation-modal');
```

## Testing

**Test file naming:** `test_<module_name>.py`

**Test structure:**
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.parsers.date import parse_month

class TestParseMonth:
    def test_full_month_names(self):
        assert parse_month("January") == 1

    def test_invalid_input(self):
        assert parse_month("invalid") is None
```

**Run specific tests:**
```bash
.venv/bin/python -m pytest tests/unit/core/test_parser.py -v
.venv/bin/python -m pytest tests/unit/core/test_parser.py::TestParseMonth -v
.venv/bin/python -m pytest tests/unit/core/test_parser.py::test_specific -v
```

## Common Tasks

### Adding an API Endpoint

1. Create/modify router in `web/routers/<domain>.py`
2. Add Pydantic schema to `web/schemas.py` if needed
3. Add tests in `tests/unit/web/routers/`

```python
# web/routers/example.py
router = APIRouter(prefix="/api", tags=["example"])

@router.get("/items")
async def list_items(skip: int = 0, limit: int = 50) -> Dict[str, Any]:
    """List items with pagination."""
    ...
```

### Adding a Service

1. Create `services/<name>.py`
2. Export from `services/__init__.py`
3. Add tests in `tests/unit/services/`
4. Integrate in `web/app.py` lifespan if needed

### Adding Constants

1. Find appropriate file in `core/constants/` by domain
2. Add constant with docstring
3. Export from `core/constants/__init__.py` if widely used
4. Import in modules that need it

## Configuration

**Files:**
- `config.template.yaml` - Template with all options documented
- `local/config/config.yaml` - Active config (gitignored)
- `tests/config.test.yaml` - Test config

**Environment variables:**
- `CURATOR_CONFIG_PATH` - Config file path
- `CURATOR_DRY_RUN` - Enable dry run mode
- `DISABLE_OCR` - Disable OCR features
- `CURATOR_LOG_LEVEL` - Log level (DEBUG, INFO, WARNING, ERROR)

## Dependencies

- Python 3.13+
- FastAPI 0.104.1, SQLAlchemy 2.0.45, uvicorn
- pytest 8.0+, Black 24.0+, pylint, flake8
- Node.js (ESLint, Prettier, Stylelint)

## File References

When referencing code locations, use `file_path:line_number`:
```
The error is handled in services/file_organizer.py:142
```
