# Changelog

## v1.1.0 (Unreleased)

### New Features

#### Internet Archive Integration

Free access to millions of magazines, comics, and newspapers from archive.org.

- Native Internet Archive search provider with collection filtering
- Built-in HTTP download client (no external download manager needed)
- Support for PDF, EPUB, ZIP, and GZIP archive formats
- Automatic extraction of periodicals from collection archives
- Prioritized in search results when available
- Optional authentication for restricted items
- Direct downloads without NZB client

Configure in `config.yaml`:

```yaml
search_providers:
  - type: internet_archive
    name: Internet Archive
    enabled: true
    priority: 1
    collections:
      - magazines
      - periodicals
      - comics
```

#### Stacks

Organize periodicals into custom collections.

- Create named stacks (e.g., "Sci-Fi Magazines", "Vintage Comics")
- Add periodicals or tracking items to stacks
- View stack-specific library and tracking pages
- Custom stack covers and descriptions
- Category filtering and sorting
- Bulk operations within stacks
- Stack membership tracking

Use cases:

- Group related periodicals by theme or era
- Organize reading lists
- Separate personal vs. shared collections
- Track series across multiple periodical titles

#### Volume Support

Full volume number parsing and display throughout the application.

- Extract volume numbers from filenames and metadata
- Display volumes in search results and library
- Sort by volume in addition to date and issue
- Support for bare volume shorthand (e.g., "v12")
- Volume-aware issue discovery and tracking
- Improved matching for multi-volume series

#### Bulk Operations

Perform actions on multiple periodicals at once.

- Bulk move to different categories
- Bulk delete periodicals
- Bulk regenerate cover images
- Bulk download from search results
- Bulk add to stacks
- Operations work within stack context

#### Enhanced Cover Processing

Improved cover image extraction and display.

- Landscape PDF covers automatically cropped to right half
- Custom cover upload per periodical
- Regenerate cover images on demand
- Better thumbnail generation performance
- Cover cleanup scheduler removes orphaned images

#### Special Editions

Better handling of special edition periodicals.

- Parse special edition markers from titles
- Display special edition status in UI
- Track special editions separately or with regular issues
- Improved matching for variant covers and editions

### Improvements

#### Search & Discovery

- Cache-aware search optimization reduces provider API calls
- Improved fuzzy matching with caching for performance
- Country and language filtering in search results
- Better in-library detection to prevent duplicate downloads
- Enhanced deduplication across providers
- Issue discovery improvements for tracked periodicals

#### Parsing & Metadata

- Enhanced title parsing with better special character handling
- Improved date extraction from filenames and metadata
- Better handling of volumes in titles
- Refined special edition detection
- More robust country and language parsing
- Support for more date formats and patterns

#### Performance

- OCR processing speed improvements:
  - DPI reduction for faster processing
  - Image resizing before OCR
  - Parallel PNG generation
- Optimized fuzzy matching with result caching
- Reduced memory usage in OCR pipeline
- Better handling of large collections

#### UI/UX

- Mobile-responsive layout improvements
- Better tracking page mobile layout
- Improved sort options (by date, volume, issue, latest)
- Enhanced download queue UI
- Better breadcrumb navigation with title case
- Collapsible sections for better organization
- Month grouping fixes in library view
- Improved variant terminology and display

#### Rate Limiting & Caching

- Provider-aware retry logic
- Better rate limit detection and handling
- Cache system refactoring for reliability
- Feed sync optimization for RSS providers
- Reduced API calls with intelligent caching

#### Download Management

- Routing based on provider type (Internet Archive vs. NZB)
- Better handling of non-regular files in cleanup
- Improved download progress tracking
- Category-aware download organization
- Support for direct HTTP downloads alongside NZB

### Bug Fixes

- Fixed infinite import loops with non-regular files
- Fixed timezone handling across codebase
- Fixed month matching in partial filename parsing
- Fixed search filter application
- Fixed stack membership for special editions
- Fixed NZB category handling
- Fixed periodical sort ordering
- Fixed cache busting issues
- Fixed stale data errors in UI
- Fixed test connection for NZB clients
- Changed country mismatch from blocking to penalty-based matching
- Fixed video files with extensions in titles bypassing filters
- Replaced deprecated `datetime.utcnow()` with `utc_now()`
- Fixed missing `all_providers_rate_limited` property
- Fixed database migration for legacy provider names

### Configuration Changes

- Added `download_clients.internet_archive` section for IA downloads
- Added `collections` and `file_formats` to Internet Archive provider config
- Expanded provider priority system (lower number = higher priority)
- Added optional IA authentication (`username`, `password`)
- More detailed rate limiting controls per provider
- Enhanced OCR configuration options

### Development

- Removed verbose agent prompts from `.github/prompts/`
- Updated CI/CD pipeline
- Black formatter version update
- Enhanced test coverage for new features
- Performance benchmarking for OCR and API
- Code review and refactoring improvements

## v1.0.0

Initial release.
