# EPUB Test Files

This directory contains EPUB files used for testing the Curator application's EPUB parsing and handling features.

## Files

### sample-book.epub
A valid EPUB 3.0 file with the following characteristics:
- **Title**: Test Book for Curator
- **Author**: Test Author
- **Language**: English
- **Chapters**: 2 chapters with sample content
- **Metadata**: Complete metadata including subjects, publisher, and description
- **Structure**: Valid EPUB 3.0 structure with:
  - mimetype file (uncompressed)
  - META-INF/container.xml
  - OEBPS/content.opf (package document)
  - OEBPS/toc.ncx (NCX navigation)
  - OEBPS/nav.xhtml (EPUB 3 navigation)
  - OEBPS/chapter1.xhtml and chapter2.xhtml (content)
  - OEBPS/style.css (stylesheet)

## Usage in Tests

Use this file to test:
- EPUB metadata extraction
- Chapter parsing
- Table of contents generation
- Cover extraction (if added)
- Validation of EPUB structure
- Import and organization workflows

## Creating the EPUB

The `sample-book/` directory contains the unzipped structure. To recreate the EPUB file:

```bash
cd sample-book
zip -X0 ../sample-book.epub mimetype
zip -Xr9D ../sample-book.epub META-INF OEBPS
```

The `-X0` flag stores the mimetype uncompressed (required by EPUB spec).

## Test Coverage

This file is used by:
- `test_core_epub_utils.py` - Testing EPUB parsing utilities
- Import workflow tests - Testing file import and organization
- Metadata extraction tests - Verifying proper metadata parsing
