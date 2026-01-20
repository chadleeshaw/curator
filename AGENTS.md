# Curator - Agent Development Guide

This guide provides essential information for AI coding agents working in the Curator codebase.

## Project Overview

Curator is a modular system for discovering, downloading, and organizing periodicals (magazines, comics, newspapers) using Newsnab APIs and download clients. Built with Python 3.13 + FastAPI backend and vanilla JavaScript ES6 frontend.

## Configuration System

### Config Synchronization

The application automatically synchronizes user configuration with `config.template.yaml` on startup. This ensures:

- **User values preserved**: All custom settings are maintained
- **New options added**: Latest configuration options with defaults and documentation
- **Deprecated keys removed**: Invalid/unsupported options are cleaned up
- **Automatic backups**: `.bak` files created before modifications (format: `config.YYYYMMDD_HHMMSS.bak`)

**How it works:**

1. On startup, `ConfigLoader` calls `sync_config_on_startup()`
2. Deep merges user config into sample config structure
3. Preserves all user values while adding missing keys from sample
4. Removes deprecated top-level keys not in `VALID_CONFIG_KEYS`
5. Creates timestamped backup if changes are made

**Skipped scenarios:**

- Test config files (containing "test" in path)
- Config file doesn't exist yet
- Config is already synchronized

See `core/config_merge.py` for implementation details and `tests/unit/core/test_config_merge.py` for behavior examples.

## ⚠️ Python Environment

**CRITICAL**: Always use `.venv/bin/python` to run Python commands in this project.

```bash
# Correct ✅
.venv/bin/python -m pytest tests/
.venv/bin/python main.py
.venv/bin/python -m black --check <files>

# Incorrect ❌
python -m pytest tests/
pytest tests/
python main.py
```

The project uses a virtual environment in `.venv/` with all dependencies installed.

## Git Hooks

The project includes a pre-push hook that automatically runs `make ci-lint` before allowing pushes. This ensures all code passes CI checks before reaching GitHub.

**Install hooks:**

```bash
make install-hooks
# or
./setup-hooks.sh
```

**Skip hook (not recommended):**

```bash
git push --no-verify
```

The hook is version-controlled in `.githooks/` and automatically configured by `make install-hooks`.

## Build & Test Commands

### Running Tests

```bash
# Run all tests
.venv/bin/python -m pytest tests/

# Run specific test file
.venv/bin/python -m pytest tests/test_parser_metadata.py

# Run specific test function
.venv/bin/python -m pytest tests/test_parser_metadata.py::test_metadata_extractor_initialization

# Run specific test class
.venv/bin/python -m pytest tests/test_parser_metadata.py::TestParseMonth

# Run with verbose output and short traceback
.venv/bin/python -m pytest tests/ -v --tb=short

# Run with debugging output
.venv/bin/python -m pytest tests/test_parser_metadata.py -vv -s

# Run tests with coverage
.venv/bin/python -m pytest tests/ --cov=. --cov-report=term-missing --cov-report=html

# Quick test categories
make test-routers          # Router/API tests only
make test-quick            # Syntax check only
```

### Linting & Formatting

```bash
# Lint all code (Python + JS + CSS)
make lint

# CI linting (matches GitHub Actions exactly - recommended before pushing)
make ci-lint               # Run all linters exactly as CI does (fails on errors)

# Lint individual languages
make lint-python           # pylint + flake8
make lint-js               # ESLint
make lint-css              # Stylelint

# Auto-format code
make format                # All languages
make format-python         # Black
make format-js             # Prettier
make format-css            # Prettier

# Run formatters directly
.venv/bin/python -m black --line-length=120 <files>
.venv/bin/python -m pylint --fail-under=7.0 <files>
.venv/bin/python -m flake8 <files>
npx prettier --write <files>
npx eslint <files>
```

**Important**: Always run `make ci-lint` before pushing to ensure your code will pass GitHub CI checks. The regular `make lint` command suppresses errors, but `make ci-lint` fails exactly like CI does.

### Running the Application

```bash
# Start the application
.venv/bin/python main.py

# Or use Make
make run
```

## Code Style Guidelines

### Python

#### Imports

- Standard library imports first
- Third-party imports second
- Local imports last
- Separate groups with blank lines
- Use explicit imports, avoid wildcard `from x import *`
- Example:

```python
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from fastapi import APIRouter, HTTPException
from sqlalchemy import Column, Integer, String

from core.constants import DEFAULT_LANGUAGE
from core.parsers import sanitize_filename
```

#### Formatting

- **Line length**: 120 characters maximum
- **Indentation**: 4 spaces (no tabs)
- **Quotes**: Double quotes for strings (Black will enforce)
- **Blank lines**: 2 between top-level classes/functions, 1 within classes
- **Trailing commas**: Use in multi-line structures
- Black formatter is the source of truth - run `make format-python`

#### Type Hints

- Use type hints for function parameters and return values
- Import from `typing` module: `Dict, List, Optional, Tuple, Any`
- Example:

```python
def parse_month(month_str: str) -> Optional[int]:
    """Parse month string to number (1-12)"""
    ...

def organize_file(
    source_path: str,
    title: str,
    issue_date: datetime,
    cover_path: Optional[str] = None,
) -> Tuple[str, str]:
    ...
```

#### Docstrings

- Use triple double-quotes `"""`
- Include brief description, Args, Returns, Raises sections
- Example:

```python
def parse_filename_for_metadata(filename: str) -> Dict[str, Any]:
    """
    Extract metadata from filename.

    Args:
        filename: The filename to parse

    Returns:
        Dictionary with extracted metadata fields

    Raises:
        ValueError: If filename format is invalid
    """
```

#### Naming Conventions

- **Modules**: lowercase with underscores (`file_organizer.py`)
- **Classes**: PascalCase (`FileOrganizer`, `TitleMatcher`)
- **Functions/Variables**: snake_case (`parse_month`, `issue_date`)
- **Constants**: UPPER_SNAKE_CASE (`DEFAULT_LANGUAGE`, `MAX_VALID_YEAR`)
- **Private**: prefix with underscore (`_session_factory`, `_parse_internal`)

#### Constants

- **ALWAYS define constants in `core/constants/` directory**, organized by domain
- **NEVER define constants in parser/utility modules** - import them instead
- Constants are organized by domain in separate files:
  - `core/constants/date.py` - Date/month mappings, year validation
  - `core/constants/language.py` - Language codes, indicators
  - `core/constants/country.py` - Country codes, mappings
  - `core/constants/files.py` - File extensions, MIME types
  - `core/constants/app.py` - Application-wide settings
  - etc.

Example of proper constant usage:

```python
# ❌ WRONG - Don't define constants in utility modules
# core/parsers/date.py
MONTH_TO_NUMBER = {"jan": 1, "feb": 2, ...}  # Bad!

def parse_month(month_str: str) -> int:
    return MONTH_TO_NUMBER.get(month_str.lower(), 0)

# ✅ CORRECT - Import constants from constants directory
# core/parsers/date.py
from core.constants.date import MONTH_TO_NUMBER, NUMBER_TO_MONTH

def parse_month(month_str: str) -> int:
    """Parse month string to number using centralized constants."""
    return MONTH_TO_NUMBER.get(month_str.lower(), 0)
```

When adding new constants:

1. Determine the appropriate constants file by domain
2. Add constant with descriptive docstring
3. Export from `core/constants/__init__.py` if widely used
4. Import in modules that need it
5. Update tests to use the centralized constant

```python
# core/constants/date.py
MONTH_TO_NUMBER = {
    "jan": 1,
    "january": 1,
    # ... more mappings
}
"""Month name/abbreviation to number mapping (case-insensitive)"""

MIN_VALID_YEAR = 1900
"""Minimum valid year for publication dates"""
```

#### Error Handling

- Use specific exception types
- Log errors with appropriate level (error, warning, info)
- Provide context in error messages
- **NEVER catch exceptions without using them** - if you don't need the exception variable, use bare `except Exception:`
- Example:

```python
if not source.exists():
    raise FileNotFoundError(f"Source file not found: {source_path}")

# ✅ CORRECT - Using the exception variable
try:
    result = process_file(path)
except ValueError as e:
    logger.error(f"Failed to process {path}: {e}")
    raise

# ✅ CORRECT - Not using exception variable, so don't capture it
try:
    result = process_file(path)
except ValueError:
    logger.error(f"Failed to process {path}")
    return None

# ❌ WRONG - Capturing but not using exception variable
try:
    result = process_file(path)
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

**CRITICAL**: Keep the codebase clean and maintainable by avoiding unused code.

- **No unused imports**: Remove imports that are never used in the file
- **No unused variables**: Remove variables that are assigned but never read
- **No unused functions**: Remove functions that are defined but never called
- **Regular cleanup**: Run `autoflake` to detect and remove unused code

```bash
# Check for unused imports and variables
.venv/bin/python -m autoflake --check --remove-all-unused-imports --remove-unused-variables <file>

# Automatically fix unused imports and variables
.venv/bin/python -m autoflake --in-place --remove-all-unused-imports --remove-unused-variables <file>
```

**Common mistakes to avoid:**

```python
# ❌ WRONG - Unused imports
import re  # Never used in file
from pathlib import Path  # Never used
from typing import Optional, List  # Only Optional is used

# ✅ CORRECT - Only import what you use
from typing import Optional

# ❌ WRONG - Unused variable
def process_data(items):
    count = len(items)  # Assigned but never used
    return [x * 2 for x in items]

# ✅ CORRECT - Remove unused variable
def process_data(items):
    return [x * 2 for x in items]

# ❌ WRONG - Unused exception variable
try:
    data = fetch_data()
except ValueError as e:  # 'e' is captured but never used
    return None

# ✅ CORRECT - Don't capture unused exception
try:
    data = fetch_data()
except ValueError:
    return None

# ❌ WRONG - Unused function (defined but never called)
def helper_function(x):
    """This function is never called anywhere"""
    return x * 2

# ✅ CORRECT - Remove unused functions entirely
# (or call them if they're actually needed)
```

**Before committing:**

1. Run `make ci-lint` to catch unused imports (flake8 will warn about F401)
2. Use `autoflake` to automatically clean up unused code
3. Verify all tests still pass after cleanup
4. Review what was removed to ensure nothing important was deleted

### JavaScript

#### Module System

- Use ES6 modules (`import`/`export`)
- Named exports for utilities, default for classes
- Example:

```javascript
// errors.js
export class APIError extends Error { ... }
export class ValidationError extends Error { ... }

// api.js
import { AuthManager } from './auth.js';
import { APIError, NetworkError } from './errors.js';

export class APIClient { ... }
```

#### Formatting

- **Line length**: 100 characters (Prettier)
- **Indentation**: 2 spaces
- **Quotes**: Single quotes for strings
- **Semicolons**: Required
- **Trailing commas**: ES5 style

#### Naming Conventions

- **Classes**: PascalCase (`APIClient`, `AuthManager`)
- **Functions/Variables**: camelCase (`authenticatedFetch`, `isDescending`)
- **Constants**: UPPER_SNAKE_CASE (`API_BASE_URL`)
- **Private/Internal**: prefix with underscore (`_token`, `_AuthenticationError`)

#### JSDoc Comments

- Use JSDoc for all exported functions and classes
- Include `@param`, `@returns`, `@throws`, `@example`
- Example:

```javascript
/**
 * Perform a GET request to the specified URL
 *
 * @param {string} url - The API endpoint URL
 * @returns {Promise<Response|null>} The fetch response or null if redirected
 * @throws {APIError} When the server returns a non-OK response
 * @throws {NetworkError} When the network request fails
 *
 * @example
 * const response = await APIClient.get('/api/periodicals?page=1');
 * const { periodicals } = await response.json();
 */
static async get(url) {
  return this.authenticatedFetch(url);
}
```

#### Error Handling

- Use custom error classes from `errors.js`
- Provide user-friendly messages via `toUserMessage()`
- Log errors to console with context
- Example:

```javascript
try {
  const response = await fetch(url);
  if (!response.ok) {
    throw new APIError(`HTTP ${response.status}`, response.status, url);
  }
} catch (error) {
  console.error(`[APIClient] Request failed for ${url}:`, error);
  throw new NetworkError(`Failed to connect`, url, error);
}
```

#### User Confirmation Dialogs

- **NEVER use JavaScript `confirm()`, `alert()`, or `prompt()`**
- **ALWAYS use modal dialogs** from `UIUtils` for confirmations
- Modals provide better UX and match the application's design system
- Example:

```javascript
// ❌ WRONG - Do not use JavaScript confirm()
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

Modal HTML structure:

```html
<div id="my-confirmation-modal" class="modal hidden">
  <div class="modal-content delete-modal-content" style="max-width: 600px">
    <h3 class="delete-modal-title">⚠️ Confirm Action</h3>
    <p class="delete-modal-subtitle">Are you sure you want to do this?</p>

    <div class="flex gap-10 justify-end">
      <button type="button" onclick="closeConfirmationModal()" class="save-btn btn-cancel flex-0">
        Cancel
      </button>
      <button type="button" onclick="confirmAction()" class="save-btn btn-delete flex-0">
        Confirm
      </button>
    </div>
  </div>
</div>
```

## Architecture Patterns

### Project Structure

```
curator/
├── core/           # Core utilities (config, auth, database, parsers)
├── models/         # Database models (SQLAlchemy)
├── providers/      # Search providers (Newsnab, RSS)
├── clients/        # Download clients (SABnzbd, NZBGet)
├── services/       # Business logic (file import, organization, OCR)
├── scheduler/      # Background tasks (download monitor, OCR processor)
├── web/            # FastAPI app, routers, middleware, schemas
├── static/         # Frontend assets (JS, CSS, templates)
├── tests/          # Test suite (pytest)
└── main.py         # Application entry point
```

### Backend Patterns

#### FastAPI Routers

- Located in `web/routers/`
- Use dependency injection for database sessions
- Return typed responses with schemas
- Example:

```python
router = APIRouter(prefix="/api", tags=["periodicals"])

@router.get("/periodicals")
async def list_periodicals(
    skip: int = 0,
    limit: int = 50
) -> Dict[str, Any]:
    """List periodicals with pagination"""
    db_session = _session_factory()
    try:
        results = db_session.query(Magazine).offset(skip).limit(limit).all()
        return {"periodicals": [r.to_dict() for r in results]}
    finally:
        db_session.close()
```

#### Database Models

- Use SQLAlchemy ORM with declarative base
- Models in `models/database.py`
- Include `created_at`, `updated_at` timestamps
- Provide `to_dict()` methods for serialization

#### Services

- Stateful classes with configuration in `__init__`
- Single responsibility (FileOrganizer, FileImporter, OCRService)
- Return tuples or dicts with results
- Log all significant operations

### Frontend Patterns

#### API Communication

- Use `APIClient` class from `api.js`
- Automatic auth token handling
- Consistent error handling with custom error classes
- Example:

```javascript
import { APIClient } from './api.js';

async function loadPeriodicals() {
  try {
    const response = await APIClient.get('/api/periodicals');
    const data = await response.json();
    renderPeriodicals(data.periodicals);
  } catch (error) {
    console.error('Failed to load:', error);
    showError(error.toUserMessage ? error.toUserMessage() : error.message);
  }
}
```

## Testing Guidelines

### Test Structure

- One test file per module: `test_<module_name>.py`
- Test classes group related tests: `class TestParseMonth:`
- Test functions are descriptive: `test_parse_full_month_names()`

### Test Patterns

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.parsers.metadata import MetadataExtractor

def test_metadata_extraction():
    """Test extracting metadata from filename"""
    extractor = MetadataExtractor()
    result = extractor.extract(Path("Magazine - Jan2024.pdf"))

    assert result is not None
    assert result.title == "Magazine"
    assert result.year == 2024
```

### Running Individual Tests

```bash
# Specific file
.venv/bin/python -m pytest tests/test_parser_metadata.py -v

# Specific test function
.venv/bin/python -m pytest tests/test_parser_metadata.py::test_metadata_extraction -v

# Specific test class
.venv/bin/python -m pytest tests/test_parser_metadata.py::TestParseMonth -v

# With debugging output
.venv/bin/python -m pytest tests/test_parser_metadata.py -vv -s
```

## Common Tasks

### Adding a New API Endpoint

1. Create route in appropriate `web/routers/<name>.py` file
2. Add schema to `web/schemas.py` if needed
3. Add tests in `tests/test_routers_<name>.py`
4. Update router documentation with docstrings

### Adding a New Parser

1. Create module in `core/parsers/<name>.py`
2. Export from `core/parsers/__init__.py`
3. Add comprehensive tests in `tests/test_parser_<name>.py`
4. Document with docstrings and type hints

### Adding a New Service

1. Create class in `services/<name>.py`
2. Follow dependency injection pattern (config in **init**)
3. Export from `services/__init__.py`
4. Add tests in `tests/test_service_<name>.py`
5. Integrate in `web/app.py` lifespan

### Running Python Scripts

Always prefix with `.venv/bin/python`:

```bash
.venv/bin/python main.py
.venv/bin/python -m pytest tests/
.venv/bin/python -c "import sys; print(sys.version)"
```

## File References in Communication

When referencing code locations, use the format `file_path:line_number` to help users navigate:

```
The error is handled in services/file_importer.py:142
```

## Configuration

### Environment Variables

- `CURATOR_CONFIG_PATH`: Custom config file location
- `CURATOR_DRY_RUN`: Set to `true` to enable dry run mode for reorganization (default: `false`)
- `DISABLE_OCR`: Set to `true` to disable OCR features
- `USE_GPU`: Set to `0` for CPU-only mode (default)

### Config Files

- `config.template.yaml`: Sample configuration template
- `local/config/config.yaml`: Active configuration (gitignored)
- `tests/config.test.yaml`: Test configuration (do not edit)

## Dependencies

- Python 3.13+ required
- FastAPI 0.104.1, SQLAlchemy 2.0.45
- pytest 8.0.0+ for testing
- Black 24.0.0+ for formatting
- Node.js for frontend tooling (ESLint, Prettier, Stylelint)

## Installation

```bash
# Install Python dependencies
pip install -r requirements.txt

# Install Node.js dependencies
npm install

# Or use Make
make install
```

---

**Remember**: Always run tests and formatters before committing! Use `make format` and `make lint` to ensure code quality. And always use `.venv/bin/python` for Python commands.
