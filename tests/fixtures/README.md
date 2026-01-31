# Test Fixtures

This directory contains test fixture files used across the test suite.

## Structure

```
fixtures/
├── pdf/        # Sample PDF files for testing
├── epub/       # Sample EPUB files for testing
└── png/        # Sample image files for testing
```

## Usage

These fixtures are used by tests that need actual file artifacts to work with.
Access them in tests using:

```python
from pathlib import Path

fixtures_dir = Path(__file__).parent.parent / "fixtures"
pdf_path = fixtures_dir / "pdf" / "NationalGeographic 2000-01.pdf"
```

Or use the conftest.py fixtures for common file paths.

## Adding New Fixtures

When adding new test fixtures:

1. Place them in the appropriate subdirectory (pdf/, epub/, png/)
2. Use small, minimal sample files when possible
3. Document any special characteristics in this README
4. Consider adding a fixture function in conftest.py for easy access

## Existing Fixtures

### PDFs

- `NationalGeographic 2000-01.pdf` - Sample magazine PDF for parser/importer tests

### EPUBs

- `sample-book.epub` - Basic EPUB for testing EPUB processing
- `sample-book/` - Extracted EPUB contents

### PNGs

- `comic.png` - Sample comic cover image
- `magazine.png` - Sample magazine cover image
