# Curator Workflow Documentation

Complete workflow documentation from tracking a periodical through download, import, and organization.

## Table of Contents

1. [User Adds Tracking for a Periodical](#1-user-adds-tracking-for-a-periodical)
2. [Adaptive Search Scheduler Selects Periodicals](#2-adaptive-search-scheduler-selects-periodicals)
3. [Search Providers for Issues](#3-search-providers-for-issues)
4. [Issue Discovery & Tracking System](#4-issue-discovery--tracking-system)
5. [Download Queue Processing](#5-download-queue-processing)
6. [Submit to Download Client](#6-submit-to-download-client)
7. [Download Monitor Tracks Progress](#7-download-monitor-tracks-progress)
8. [File Import & Organization](#8-file-import--organization)
9. [OCR Processing (Background)](#9-ocr-processing-background)
10. [Search Statistics Update](#10-search-statistics-update)

---

## Visual Workflow Overview

### Main Tracking → Download → Import Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. USER ADDS TRACKING                                            │
│    POST /api/periodicals/track                                   │
│    → Creates MagazineTracking record                             │
│    → Generates OLID (Open Library ID)                            │
└─────────────────────┬───────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. ADAPTIVE SEARCH SCHEDULER (Background Task)                   │
│    services/search_scheduler.py                                  │
│    → Selects 1-2 periodicals to search per run                   │
│    → Priority: Never searched > Overdue > Recently successful    │
│    → Adaptive intervals: 1h (rapid) → 6h → 24h → 7 days          │
└─────────────────────┬───────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. SEARCH PROVIDERS                                              │
│    services/download_manager.py                                  │
│    → Queries Newsnab/RSS providers                               │
│    → Filters by language/country/edition                         │
│    → Returns search results with metadata                        │
└─────────────────────┬───────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4a. ISSUE DISCOVERY - Record Results                             │
│     services/issue_discovery.py                                  │
│     → Parse metadata from search results                         │
│     → Generate fuzzy match group (deduplication)                 │
│     → Create/update DiscoveredIssue record                       │
│     → Status: "discovered"                                       │
└─────────────────────┬───────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4b. ISSUE DISCOVERY - Evaluate Against Rules                     │
│     services/issue_discovery.py                                  │
│     → Check if already in library → "completed"                  │
│     → Check tracking rules:                                      │
│       • track_all_editions = True → "wanted"                     │
│       • track_new_only = True + current date → "wanted"          │
│       • selected_years contains year → "wanted"                  │
│       • Else → "ignored"                                         │
│     → Calculate priority (1-100, higher = download first)        │
└─────────────────────┬───────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────────────────┐
│ 5. DOWNLOAD QUEUE PROCESSING                                     │
│    services/download_manager.py                                  │
│    → Get queue ordered by priority DESC, first_seen ASC          │
│    → Check concurrent download limit (default: 10)               │
│    → Submit issues to download client                            │
└─────────────────────┬───────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────────────────┐
│ 6. SUBMIT TO DOWNLOAD CLIENT                                     │
│    clients/sabnzbd.py or clients/nzbget.py                       │
│    → Submit NZB URL to download client                           │
│    → Create DownloadSubmission record (status: PENDING)          │
│    → Update DiscoveredIssue (status: "queued")                   │
│    → Create sidecar file (filename.pdf.curator_meta.json)        │
└─────────────────────┬───────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────────────────┐
│ 7. DOWNLOAD MONITOR (Background Task - 30s interval)             │
│    tasks/download_monitor.py                                     │
│    → Poll download client for job status                         │
│    → Update DownloadSubmission: PENDING → DOWNLOADING →          │
│      COMPLETED/FAILED                                            │
│    → Scan downloads folder for new files                         │
│    → Trigger file import when complete                           │
└─────────────────────┬───────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────────────────┐
│ 8a. FILE IMPORT - Find Files                                     │
│     services/importer/importer.py                                │
│     → Scan downloads directory for PDF/EPUB/CBZ/CBR              │
│     → Skip blacklisted/invalid files                             │
└─────────────────────┬───────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────────────────┐
│ 8b. FILE IMPORT - Extract Metadata (Priority Order)              │
│     1. Read sidecar file (tracking_id, metadata)                 │
│     2. Text scan (native PDF/EPUB text extraction)               │
│     3. OCR (image-based PDFs, CBZ, CBR)                          │
│     4. Filename parsing (fallback)                               │
│     → Aggregate all sources with weighted confidence             │
└─────────────────────┬───────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────────────────┐
│ 8c. FILE IMPORT - Match to Tracking                              │
│     → If sidecar exists: Use tracking_id from sidecar            │
│     → Else: Fuzzy match title against tracked periodicals        │
│     → Confidence threshold: 80%                                  │
└─────────────────────┬───────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────────────────┐
│ 8d. FILE IMPORT - Organize File                                  │
│     services/file_organizer.py                                   │
│     → Build filename: "{title} - {month}{year}.{ext}"            │
│     → Build directory: "{category}/{title}/{year}/"              │
│     → Extract cover image (first page/image)                     │
│     → Move file and cover to organized location                  │
└─────────────────────┬───────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────────────────┐
│ 8e. FILE IMPORT - Create Database Record                         │
│     → Calculate content hash (SHA256) for deduplication          │
│     → Create Magazine record with all metadata                   │
│     → Link to MagazineTracking (tracking_id)                     │
│     → Update DiscoveredIssue (status: "completed")               │
└─────────────────────┬───────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────────────────┐
│ 8f. FILE IMPORT - Cleanup                                        │
│     → Delete original file from downloads                        │
│     → Delete sidecar file                                        │
│     → Delete from download client (if configured)                │
│     → Mark DownloadSubmission as processed                       │
└─────────────────────────────────────────────────────────────────┘
```

---

## 1. User Adds Tracking for a Periodical

**Entry Point:** `web/routers/tracking/crud.py:49` - `start_tracking_periodical()`

**Process:**

1. User provides: `title`, `category`, `country`, `language`
2. System generates an OLID (Open Library ID) from title: `core/utils/general.py` - `generate_olid()`
3. Creates `MagazineTracking` record in database: `models/database.py:103-179`

**Key fields initialized:**

- `olid`, `title`, `language`, `country`
- `track_all_editions` = False (default)
- `track_new_only` = False (default)
- `selected_editions` = {} (empty dict)
- `selected_years` = [] (empty list)
- `search_interval_hours` = 6 (default normal interval)
- `last_searched` = NULL (never searched yet)

**Database Table:** `periodical_tracking`

**API Endpoint:** `POST /api/periodicals/track`

---

## 2. Adaptive Search Scheduler Selects Periodicals

**Service:** `services/search_scheduler.py:62` - `SearchScheduler.select_periodicals_to_search()`

**How It Works:**

- **Does NOT search ALL periodicals every run** (old design)
- Uses adaptive scheduling to search 1-2 periodicals per run
- **Selection Priority:**
  1. Never searched before (`last_searched IS NULL`)
  2. Overdue for search (based on `search_interval_hours`)
  3. Recently successful (found new issues)

**Adaptive Intervals:**

- **Rapid (1 hour):** Just found new issues
- **Normal (6 hours):** Default
- **Slow (24 hours):** 3-5 consecutive empty searches
- **Very Slow (7 days):** 6+ consecutive empty searches

**Task Scheduler:** `web/app.py:217` - `auto_download_task()` calls this periodically

---

## 3. Search Providers for Issues

**Service:** `services/download_manager.py:68` - `DownloadManager.search_periodical_issues()`

**Process:**

1. Searches configured providers (Newsnab, RSS): `providers/newsnab.py`, `providers/rss.py`
2. Parses search results: `core/parsers/search_result.py`
3. Filters by:
   - Language/country: `web/routers/search.py:131` - `_filter_by_language_and_country()`
   - Edition variants: `web/routers/search.py:69` - `_filter_edition_variants()`
4. Returns list of search results with metadata

**Search Results Structure:**

```python
{
    "title": "Magazine - January 2024",
    "url": "https://provider.com/nzb/12345",
    "provider": "NZBGeek",
    "publication_date": datetime(2024, 1, 1),
    "raw_metadata": {...}
}
```

---

## 4. Issue Discovery & Tracking System

**Service:** `services/issue_discovery.py:44` - `IssueDiscoveryService.record_search_results()`

**This is the unified system replacing scattered download logic**

### 4a. Record Discovered Issues

**Process:**

1. For each search result:
   - Parse title to extract metadata: `core/parsers/metadata.py`
   - Generate fuzzy match group ID for deduplication: `issue_discovery.py:403`
   - Check if already discovered (by `tracking_id` + `fuzzy_match_group`)

2. **If existing:** Update record
   - Increment `times_seen`
   - Update `last_seen`
   - Update `latest_url` and `latest_provider`

3. **If new:** Create `DiscoveredIssue` record
   - `download_status` = "discovered"
   - `download_priority` = 50 (default middle priority)
   - Store all metadata (title, date, language, etc.)

**Database Table:** `discovered_issues` (`models/database.py:350-449`)

### 4b. Evaluate Against Tracking Rules

**Service:** `issue_discovery.py:209` - `IssueDiscoveryService.evaluate_discovered_issues()`

**Process:**

1. Query all issues with `download_status = "discovered"`
2. For each issue:
   - **Check if already in library:** `issue_discovery.py:515` - `_check_if_in_library()`
     - If YES → status = "completed", priority = 0
   - **Check if matches tracking rules:** `issue_discovery.py:435` - `_should_download()`
     - `track_all_editions = True` → DOWNLOAD
     - `track_new_only = True` → Download if current/future date
     - `selected_years` contains issue year → DOWNLOAD
     - Otherwise → IGNORE
   - **Calculate priority:** `issue_discovery.py:471` - `_calculate_priority()`
     - Recency: +30 for <7 days, +20 for <30 days, +10 for <90 days
     - Frequency: +10 max for issues seen multiple times
     - Tracking preferences: +10 for `track_all_editions`
     - **Range:** 1-100 (higher = download first)

3. **Update status:**
   - "wanted" → Ready for download
   - "ignored" → Doesn't match criteria
   - "completed" → Already have it

---

## 5. Download Queue Processing

**Service:** `services/download_manager.py:1200` - `DownloadManager.process_queue()`

**Process:**

1. Check concurrent download limit (default: 10)
2. Get download queue: `issue_discovery.py:335` - `IssueDiscoveryService.get_download_queue()`
   - Ordered by: `download_priority DESC`, `first_seen ASC`
   - Statuses: "wanted" or "failed" (retryable)
3. For each issue in queue (up to available slots):
   - Submit to download manager: `download_manager.py:487` - `submit_from_discovered_issue()`

**Task:** `web/app.py:295` - Auto-download task calls this in Phase 3

---

## 6. Submit to Download Client

**Service:** `services/download_manager.py:487` - `DownloadManager.submit_from_discovered_issue()`

**Process:**

1. Validate issue has URL and is not permanently failed
2. Check concurrent download limit
3. Get download category from tracking record or config
4. Submit NZB to download client: `clients/sabnzbd.py` or `clients/nzbget.py`
5. **Create `DownloadSubmission` record:** `models/database.py:213-263`
   - `status` = "PENDING"
   - `job_id` = client's job ID
   - `tracking_id` = which periodical
   - `source_url` = NZB URL
   - `fuzzy_match_group` = for deduplication
6. **Update `DiscoveredIssue`:**
   - `download_status` = "queued"
   - `current_submission_id` = submission.id
   - Append to `submission_ids` history
   - Increment `attempt_count`

**Database Tables:** `download_submissions`, `discovered_issues`

---

## 7. Download Monitor Tracks Progress

**Task:** `tasks/download_monitor.py:71` - `DownloadMonitor.run()`

**Runs periodically (every 30 seconds by default)**

### 7a. Monitor Download Client

**Process:** `download_monitor.py:230` - `_monitor_download_client()`

1. **Update pending downloads:** `download_monitor.py:313`
   - Query all submissions with status = PENDING or DOWNLOADING
   - For each submission:
     - Get status from client: `download_client.get_status(job_id)`
     - Map to internal status: PENDING, DOWNLOADING, COMPLETED, FAILED
     - Update `DownloadSubmission` record
     - **If FAILED:**
       - Increment `attempt_count`
       - Record error in `last_error`
       - Check if `attempt_count > max_retries` → mark as bad file
       - Delete from client if `delete_from_client_on_completion = True`

2. **Process completed downloads:** `download_monitor.py:395`
   - Query submissions with status = COMPLETED
   - For each completed download, trigger file import (see step 8)

### 7b. Scan Downloads Folder

**Process:** `download_monitor.py:261` - `_scan_downloads_folder()`

1. Recursively find all PDF/EPUB/CBZ/CBR files in downloads directory
2. Call file importer to process them (handles files from ANY source, not just download client)

---

## 8. File Import & Organization

**Service:** `services/importer/importer.py` - `FileImporter.process_downloads()`

**This handles files from BOTH download client AND manual uploads**

### 8a. Find Files to Import

**Process:**

1. Scan downloads directory for PDF/EPUB/CBZ/CBR files
2. Skip files that are:
   - Already being processed (tracked in memory)
   - Blacklisted extensions
   - Invalid/corrupt

### 8b. Extract Metadata

**Service:** `services/importer/importer.py` - `FileImporter._extract_metadata()`

**Multi-source metadata extraction:**

1. **Check for sidecar file:** `services/importer/sidecar.py:63` - `read_sidecar_file()`
   - Format: `filename.pdf.curator_meta.json`
   - Contains: `tracking_id`, `tracking_title`, `country`, `language`
   - Created during download submission for tracking association

2. **Text scan (native PDFs/EPUBs):** `services/text_scan_service.py:129` - `TextScanService.scan_document()`
   - Extracts embedded text from PDF/EPUB (not OCR)
   - Parses year, month, volume, issue from text
   - Fast and accurate for text-based documents

3. **OCR (image-based PDFs/CBZ/CBR):** `services/ocr/service.py`
   - Creates OCR job in `ocr_jobs` table
   - Background processor handles OCR: `tasks/ocr_processor.py`
   - Extracts text from images
   - Parses metadata from OCR text

4. **Filename parsing:** `core/parsers/metadata.py` - `MetadataExtractor`
   - Fallback if other methods fail
   - Parses title, date, issue number from filename

5. **Aggregate metadata:** `services/importer/importer.py` - `_aggregate_metadata()`
   - Combines all sources with weighted confidence
   - Prioritizes: sidecar > text_scan > OCR > filename

### 8c. Determine Tracking Association

**Process:**

1. **If sidecar exists:** Use `tracking_id` from sidecar (most reliable)
2. **Else:** Match title against tracked periodicals: `core/parsers/matcher.py` - `TitleMatcher.match()`
   - Fuzzy string matching (threshold: 80 by default)
   - Returns best match + confidence score

### 8d. Organize File

**Service:** `services/file_organizer.py:285` - `FileOrganizer.organize()`

**Process:**

1. Build filename: `file_organizer.py:122` - `_build_filename()`
   - Pattern: `{title} - {month}{year}.{ext}`
   - Example: `Wired - December2024.pdf`
   - Optional: Include volume/issue numbers

2. Build directory structure: `file_organizer.py:174` - `_build_default_directory()`
   - Default: `{category}/{title}/{year}/`
   - Example: `_Magazines/Wired/2024/`
   - Supports custom patterns via config

3. Extract cover image: `file_organizer.py:362` - `extract_cover_from_pdf()`
   - Supports: PDF, EPUB, CBZ, CBR
   - Saves as: `{filename}.jpg`
   - Uses: `core/utils/pdf.py`, `core/utils/epub.py`, `core/utils/cbz.py`

4. Move file to organized location
5. Move cover image

### 8e. Create Database Record

**Process:**

1. Calculate content hash (SHA256) for deduplication: `core/utils/general.py`
2. Create `Magazine` record: `models/database.py:67-101`
   - `title` = extracted title
   - `issue_date` = extracted date
   - `language` = detected language
   - `file_path` = organized path
   - `cover_path` = cover image path
   - `content_hash` = SHA256 of file
   - `tracking_id` = linked tracking record
   - `extra_metadata` = all extracted metadata (JSON)
3. **Update `DiscoveredIssue` (if from tracking system):**
   - `download_status` = "completed"
   - `magazine_id` = new Magazine.id

### 8f. Cleanup

**Process:**

1. Delete original file from downloads folder
2. Delete sidecar file (if exists)
3. **Update `DownloadSubmission`:**
   - Mark as processed (`file_path = NULL`)
4. **Delete from download client (if configured):**
   - Check `MagazineTracking.delete_from_client_on_completion`
   - If TRUE: `download_client.delete(job_id)`

---

## 9. OCR Processing (Background)

**Task:** `tasks/ocr_processor.py` - `OCRProcessor`

**Runs periodically (independent of download monitor)**

### Process:

1. Query `ocr_jobs` table for jobs with status = PENDING
2. Order by priority (HIGH > NORMAL > LOW)
3. Process in batches (default: 5 at a time)
4. For each job:
   - Extract images from PDF/CBZ/CBR: `core/utils/pdf.py`, `core/utils/cbz.py`
   - Run OCR: `services/ocr/service.py` - `OCRService.scan_document()`
   - Extract metadata from OCR text
   - Update `Magazine.extra_metadata` with OCR results
   - Mark job as COMPLETED or FAILED
5. Store results in `OCRJob.ocr_metadata` (JSON)

---

## 10. Search Statistics Update

**Service:** `services/search_scheduler.py:119` - `SearchScheduler.update_search_stats()`

**Called after each search run**

**Process:**

1. Update `MagazineTracking` record:
   - `last_searched` = NOW
   - `search_count` += 1
   - `total_issues_discovered` += new_issues_found
   - **If new issues found:**
     - `last_discovery_count` = new_issues_found
     - `last_discovery_date` = NOW
     - `searches_without_new_issues` = 0 (reset)
     - `search_interval_hours` = RAPID (1 hour)
   - **If no new issues:**
     - `searches_without_new_issues` += 1
     - Adjust `search_interval_hours` based on consecutive empty searches:
       - 0 empty → RAPID (1h)
       - 1-2 empty → NORMAL (6h)
       - 3-5 empty → SLOW (24h)
       - 6+ empty → VERY SLOW (168h)

This adaptive scheduling ensures:

- Active periodicals are searched frequently
- Inactive periodicals don't waste resources
- System scales to hundreds of tracked periodicals

---

## Additional Workflows

### OCR Processing Workflow (Parallel to Import)

```
┌─────────────────────────────────────────────────────────────────┐
│ File Import detects image-based PDF/CBZ/CBR                      │
└─────────────────────┬───────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────────────────┐
│ Create OCRJob record (status: PENDING, priority: HIGH/NORMAL)    │
│ models/database.py:301                                           │
└─────────────────────┬───────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────────────────┐
│ OCR PROCESSOR (Background Task - Independent)                    │
│ tasks/ocr_processor.py                                           │
│ → Query pending OCR jobs ordered by priority                     │
│ → Process in batches (default: 5 at a time)                      │
└─────────────────────┬───────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────────────────┐
│ OCR Service - Extract Text from Images                           │
│ services/ocr/service.py                                          │
│ → Extract images from PDF/CBZ/CBR                                │
│ → Run OCR engine (Tesseract)                                     │
│ → Parse metadata from OCR text                                   │
└─────────────────────┬───────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────────────────┐
│ Update Magazine.extra_metadata with OCR results                  │
│ → Store OCR text in OCRJob.ocr_metadata                          │
│ → Mark OCRJob as COMPLETED/FAILED                                │
└─────────────────────────────────────────────────────────────────┘
```

### Search Statistics & Adaptive Scheduling

```
┌─────────────────────────────────────────────────────────────────┐
│ After each search completes                                      │
│ services/search_scheduler.py:119                                 │
└─────────────────────┬───────────────────────────────────────────┘
                      ↓
                 ┌────────┐
                 │ Found  │
                 │ Issues?│
                 └────┬───┘
                      │
         ┌────────────┴────────────┐
         │ YES                     │ NO
         ↓                         ↓
┌────────────────────┐    ┌────────────────────┐
│ • last_discovery   │    │ • searches_without │
│   _count = N       │    │   _new_issues += 1 │
│ • last_discovery   │    │ • Adjust interval: │
│   _date = NOW      │    │   0 empty → 1h     │
│ • search_interval  │    │   1-2 → 6h         │
│   = 1h (RAPID)     │    │   3-5 → 24h        │
│ • searches_without │    │   6+ → 7 days      │
│   _new_issues = 0  │    │                    │
└────────────────────┘    └────────────────────┘
```

### Manual File Import Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│ User manually adds files to downloads directory                  │
└─────────────────────┬───────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────────────────┐
│ Download Monitor scans downloads folder (30s interval)           │
│ tasks/download_monitor.py:261                                    │
└─────────────────────┬───────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────────────────┐
│ File Importer processes files (same as step 8 above)             │
│ → Extract metadata (no sidecar, relies on text/OCR/filename)    │
│ → Fuzzy match title to tracked periodicals                       │
│ → Organize and create Magazine record                            │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Data Flow Diagram

### Tracking → Download → Import

```
User Tracks Periodical
    ↓
MagazineTracking (DB)
    ↓
SearchScheduler selects periodicals to search (adaptive)
    ↓
DownloadManager searches providers
    ↓
IssueDiscoveryService records results
    ↓
DiscoveredIssue (DB) - status: "discovered"
    ↓
IssueDiscoveryService evaluates against rules
    ↓
DiscoveredIssue (DB) - status: "wanted" (if matches)
    ↓
DownloadManager.process_queue() submits to client
    ↓
DownloadSubmission (DB) - status: "PENDING"
    ↓
DownloadMonitor polls client
    ↓
DownloadSubmission (DB) - status: "COMPLETED"
    ↓
FileImporter processes file
    ↓
Magazine (DB) - organized file in library
    ↓
DiscoveredIssue (DB) - status: "completed"
```

### Metadata Extraction Priority

```
Sidecar File (highest confidence)
    ↓ (if missing)
Text Scan (native PDF/EPUB text)
    ↓ (if no text or image-based)
OCR (image extraction)
    ↓ (fallback)
Filename Parsing (lowest confidence)
    ↓
Aggregate all sources → Final metadata
```

---

## Key Workflow Characteristics

### Adaptive & Intelligent

- Searches 1-2 periodicals per run (not all at once)
- Adjusts search frequency based on success (1h → 7 days)
- Priority-based download queue (higher priority downloads first)

### Deduplication at Every Level

- Fuzzy match groups prevent duplicate issue discoveries
- Content hash prevents duplicate files in library
- Edition filtering removes variant editions of same issue

### Metadata Extraction Hierarchy

1. **Sidecar file** (highest confidence) - tracking association
2. **Text scan** (fast, accurate for native PDFs/EPUBs)
3. **OCR** (slower, for image-based documents)
4. **Filename parsing** (fallback)

### Resilient & Fault-Tolerant

- Retry failed downloads (configurable max attempts)
- Bad file tracking (permanently failed downloads)
- OCR jobs can be reprocessed independently

### Works with Multiple Sources

- Tracked downloads (via search providers)
- Manual file uploads (scans downloads directory)
- External download clients (SABnzbd, NZBGet)

---

## Critical File References

### Models (Database Schema)

- `models/database.py:103` - **MagazineTracking** (tracks periodical series)
- `models/database.py:350` - **DiscoveredIssue** (issue discovery & tracking)
- `models/database.py:213` - **DownloadSubmission** (download jobs)
- `models/database.py:67` - **Magazine** (organized periodicals in library)
- `models/database.py:301` - **OCRJob** (OCR processing queue)

### Services

- `services/search_scheduler.py:62` - Adaptive periodical search scheduling
- `services/issue_discovery.py:44` - Issue discovery & tracking system
- `services/download_manager.py:68` - Search & download management
- `services/file_organizer.py:285` - File organization & renaming
- `services/importer/importer.py` - File import & metadata extraction
- `services/text_scan_service.py:129` - Native text extraction
- `services/ocr/service.py` - OCR processing

### Tasks (Background Jobs)

- `tasks/scheduler.py` - Task scheduling framework
- `tasks/download_monitor.py:71` - Download monitoring & file scanning
- `tasks/ocr_processor.py` - OCR background processing
- `web/app.py:217` - Auto-download task (uses Issue Discovery)

### Routers (API Endpoints)

- `web/routers/tracking/crud.py:49` - Start tracking periodical
- `web/routers/tracking/preferences.py` - Update tracking preferences
- `web/routers/discovery.py:44` - List discovered issues
- `web/routers/search.py:487` - Search for periodical issues

### Parsers

- `core/parsers/metadata.py` - Filename metadata extraction
- `core/parsers/matcher.py` - Fuzzy title matching
- `core/parsers/search_result.py` - Search result parsing

---

**Last Updated:** January 20, 2026
