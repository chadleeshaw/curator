# Indexer Cache Architecture

## Overview

Local SQLite cache that mirrors provider catalogs, enabling instant searches without hitting rate-limited APIs.

## Problem Statement

**Current Issues:**

- Providers limit to 100 requests/hour (1 per 36 seconds)
- Every user search consumes an API call
- Search results cached for 7 days but initial search still hits API
- RSS feed cache (1 hour) helps but doesn't eliminate API calls

**Solution:**

- Build local searchable index of all releases
- Sync incrementally via RSS (no query parameter)
- All searches query local database (zero API calls)
- Background sync keeps index fresh (15-30 min intervals)

## Architecture

### Components

```
┌─────────────────────────────────────────────────────────────┐
│                     User Search Request                      │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                   Search Router (Modified)                   │
│  - Query local indexer_cache.db instead of providers        │
│  - Apply filters (language, country, date range)            │
│  - Return results instantly (no API calls)                  │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│              Local Indexer Cache (SQLite)                    │
│  Location: {cache_dir}/indexer_cache.db                     │
│  Tables: indexed_releases, sync_status                      │
└─────────────────────────────────────────────────────────────┘
                              ↑
┌─────────────────────────────────────────────────────────────┐
│              Background Sync Service (Periodic)              │
│  - Runs every 15-30 minutes                                 │
│  - Fetches latest 100 releases per provider (RSS mode)      │
│  - Updates local cache                                      │
│  - Tracks sync status and errors                            │
└─────────────────────────────────────────────────────────────┘
                              ↑
┌─────────────────────────────────────────────────────────────┐
│                    Prowlarr/Newsnab API                      │
│  - RSS endpoint (no query = all recent releases)            │
│  - Rate limited: 100 requests/hour                          │
└─────────────────────────────────────────────────────────────┘
```

### Database Schema

**Location:** `{cache_dir}/indexer_cache.db` (separate from main database)

#### Table: `indexed_releases`

```sql
CREATE TABLE indexed_releases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Provider info
    provider_name VARCHAR(100) NOT NULL,
    provider_type VARCHAR(50) NOT NULL,  -- 'newsnab', 'rss'

    -- Release identifiers
    guid VARCHAR(255) NOT NULL UNIQUE,  -- Provider GUID (primary dedup key)
    title VARCHAR(500) NOT NULL,

    -- Download info
    download_url VARCHAR(1000),
    info_url VARCHAR(1000),
    size_bytes BIGINT,

    -- Metadata
    publication_date DATETIME,
    category VARCHAR(100),
    language VARCHAR(50),
    country VARCHAR(50),

    -- Indexing
    normalized_title VARCHAR(500),  -- Lowercase, no special chars (for search)
    fuzzy_match_group VARCHAR(255),  -- For deduplication

    -- Timestamps
    first_seen DATETIME NOT NULL,  -- When first added to cache
    last_seen DATETIME NOT NULL,   -- Last time seen in sync

    -- Search optimization
    search_tokens TEXT,  -- Space-separated keywords for FTS

    -- Raw data
    raw_metadata JSON,

    -- Indexes
    INDEX idx_provider (provider_name),
    INDEX idx_guid (guid),
    INDEX idx_normalized_title (normalized_title),
    INDEX idx_fuzzy_group (fuzzy_match_group),
    INDEX idx_publication_date (publication_date),
    INDEX idx_last_seen (last_seen)
);

-- Full-text search index
CREATE VIRTUAL TABLE indexed_releases_fts USING fts5(
    title,
    normalized_title,
    search_tokens,
    content=indexed_releases,
    content_rowid=id
);
```

#### Table: `sync_status`

```sql
CREATE TABLE sync_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    provider_name VARCHAR(100) NOT NULL UNIQUE,

    -- Sync tracking
    last_sync_time DATETIME,
    last_successful_sync DATETIME,
    last_sync_release_guid VARCHAR(255),  -- Latest GUID seen (for incremental)
    last_sync_release_date DATETIME,      -- Latest date seen

    -- Statistics
    total_releases_cached INTEGER DEFAULT 0,
    total_syncs INTEGER DEFAULT 0,
    failed_syncs INTEGER DEFAULT 0,
    last_error TEXT,

    -- Status
    is_enabled BOOLEAN DEFAULT 1,
    sync_interval_minutes INTEGER DEFAULT 30,

    -- Initial sync
    initial_sync_completed BOOLEAN DEFAULT 0,
    initial_sync_date DATETIME,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

## Services

### 1. IndexerCacheService

**Purpose:** CRUD operations on local cache database

**Location:** `services/indexer_cache.py`

**Responsibilities:**

- Manage separate SQLite connection to `indexer_cache.db`
- Insert/update releases in cache
- Query cache for search results
- Cleanup old/stale entries
- Provide statistics

**Key Methods:**

```python
class IndexerCacheService:
    def __init__(self, cache_dir: str):
        self.db_path = Path(cache_dir) / "indexer_cache.db"
        self.engine = create_engine(f"sqlite:///{self.db_path}")

    def search(self, query: str, filters: dict) -> List[IndexedRelease]:
        """Search local cache using FTS5"""

    def upsert_releases(self, releases: List[dict], provider_name: str):
        """Insert or update releases (by GUID)"""

    def cleanup_old_releases(self, days: int = 90):
        """Remove releases not seen in X days"""

    def get_stats(self) -> dict:
        """Get cache statistics"""
```

### 2. IndexerSyncService

**Purpose:** Sync releases from providers to local cache

**Location:** `services/indexer_sync.py`

**Responsibilities:**

- Fetch releases from providers in RSS mode (no query)
- Track sync status per provider
- Handle initial full sync vs incremental sync
- Respect rate limits
- Update sync_status table

**Key Methods:**

```python
class IndexerSyncService:
    def __init__(self, providers: List, cache_service: IndexerCacheService):
        self.providers = providers
        self.cache_service = cache_service

    async def initial_sync(self, provider_name: str, category: str = None):
        """Full initial sync for a provider (may take multiple pages)"""

    async def incremental_sync(self, provider_name: str):
        """Fetch latest 100 releases (RSS mode, no query)"""

    async def sync_all_providers(self):
        """Sync all enabled providers"""

    def get_sync_status(self, provider_name: str) -> dict:
        """Get sync status for provider"""
```

### 3. Background Sync Task

**Purpose:** Periodic execution of sync service

**Location:** `tasks/indexer_sync.py` or add to existing `TaskScheduler`

**Configuration:**

```yaml
# config.yaml
indexer_cache:
  enabled: true
  sync_interval: 1800 # 30 minutes (seconds)
  initial_sync_on_startup: true
  cleanup_days: 90 # Remove releases not seen in 90 days
  max_releases_per_sync: 100 # RSS limit
```

## Search Flow

### Current Flow (Every search hits API)

```
User Search → Search Router → Providers (API Call) → Results → Apply Filters → Return
                                  ↓
                            Rate Limit Hit
```

### New Flow (Zero API calls during search)

```
User Search → Search Router → IndexerCacheService.search() → Results → Apply Filters → Return
                                         ↓
                              Local SQLite FTS Query (instant)
```

### Background Sync Flow

```
Every 30 mins:
  For each provider:
    ↓
    Check sync_status table
    ↓
    If initial_sync_completed == false:
      → Full sync (paginate all categories)
    Else:
      → Incremental sync (latest 100, no query)
    ↓
    Upsert releases to indexed_releases
    ↓
    Update sync_status table
```

## Migration Strategy

### Phase 1: Build New System (Parallel)

- ✅ Create indexer_cache.db schema
- ✅ Create IndexerCacheService
- ✅ Create IndexerSyncService
- ✅ Add background sync task
- ⚠️ Keep existing search working (don't break anything)

### Phase 2: Test & Validate

- ✅ Run initial sync for all providers
- ✅ Verify cache is populated
- ✅ Test local search accuracy vs API search
- ✅ Monitor sync reliability

### Phase 3: Switch Traffic

- ✅ Add config flag: `indexer_cache.enabled`
- ✅ If enabled, route searches to local cache
- ✅ If disabled, use existing API search (fallback)
- ✅ Monitor API call reduction

### Phase 4: Cleanup

- ✅ Remove old SearchResult caching (no longer needed)
- ✅ Add cache management UI
- ✅ Document new system

## Benefits

### Performance

- **Instant searches** - FTS5 queries are sub-millisecond
- **No API delays** - Zero network latency
- **Unlimited searches** - No rate limits

### API Usage

- **~98% reduction** - From ~100 searches/hour to ~2-4 syncs/hour
- **Predictable usage** - Scheduled syncs only
- **Rate limit safe** - Easy to stay under 100/hour

### User Experience

- **Faster results** - No waiting for API responses
- **Offline capability** - Can search even if provider is down
- **Better filtering** - Can do complex queries on local data

### Data Quality

- **Deduplication** - GUID-based dedup across all providers
- **Historical data** - Keep releases even after they expire from provider
- **Trending analysis** - Can analyze release patterns over time

## Rate Limiting Strategy

### Current Usage (Worst Case)

- 100 manual searches/hour = **100 API calls**
- 4 auto-download checks/hour × 10 periodicals = **40 API calls**
- **Total: 140 API calls/hour** → ⚠️ OVER LIMIT

### New Usage (With Cache)

- 100 manual searches/hour = **0 API calls** (local cache)
- 2 incremental syncs/hour = **2 API calls**
- 1 initial sync on startup = **10-50 API calls** (one-time, paginated)
- **Total: ~2-4 API calls/hour** → ✅ Well under limit

### Sync Schedule Options

**Conservative (30 min):**

- 2 syncs/hour × 1 provider = 2 API calls/hour
- Safe for multiple providers

**Aggressive (15 min):**

- 4 syncs/hour × 1 provider = 4 API calls/hour
- Still safe, more real-time

**Recommended:**

- Start with 30 min intervals
- Monitor API usage
- Adjust per provider if needed

## Implementation Notes

### RSS Mode (No Query)

**Newsnab API:**

```
# Regular search (uses API quota heavily)
GET /api?t=search&q=Magazine&apikey=xxx

# RSS mode (no query = latest releases)
GET /api?t=search&apikey=xxx
```

When you omit the `q=` parameter, Newsnab returns the latest releases in RSS order (newest first). This is exactly what we want for syncing.

**Prowlarr Support:**
Prowlarr proxies this to all configured indexers, so one API call to Prowlarr can sync multiple indexers (even better for rate limits).

### Deduplication Strategy

**GUID is King:**

- Use provider's `guid` field as primary key
- All providers should supply a unique GUID
- If GUID matches, update existing record (upsert)

**Fuzzy Matching (Secondary):**

- Still generate `fuzzy_match_group` for grouping similar titles
- Used for cross-provider deduplication
- Helps identify same issue from different indexers

### Cleanup Strategy

**Stale Release Removal:**

```python
# Remove releases not seen in 90 days
DELETE FROM indexed_releases
WHERE last_seen < datetime('now', '-90 days')
```

**Why 90 days?**

- Periodicals are archived longer than TV shows
- Backfilling older issues is common
- Balances storage vs data availability

### Storage Estimates

**Per Release:**

- ~2 KB per row (with JSON metadata)

**Total Storage:**

- 10,000 releases × 2 KB = **20 MB**
- 100,000 releases × 2 KB = **200 MB**
- 1,000,000 releases × 2 KB = **2 GB**

**Recommendation:**

- Start with 90-day retention
- Monitor database size
- Adjust retention if needed

## Configuration

### New Config Section

```yaml
# config.yaml
indexer_cache:
  # Enable local indexer cache (highly recommended for rate-limited providers)
  enabled: true

  # Sync interval in seconds (default: 30 minutes)
  # Lower = more real-time, higher = less API usage
  sync_interval: 1800

  # Perform initial full sync on startup (one-time, paginated)
  initial_sync_on_startup: true

  # Maximum releases to fetch per sync (RSS limit)
  max_releases_per_sync: 100

  # Remove releases not seen in X days
  cleanup_days: 90

  # Categories to sync (empty = all categories)
  # Example: ['7000', '7010', '7020', '7030']  # Magazines only
  categories: []

  # Per-provider overrides
  provider_overrides:
    Prowlarr:
      sync_interval: 1800 # 30 min
      enabled: true
```

## Testing Plan

### Unit Tests

- `test_indexer_cache_service.py` - CRUD operations
- `test_indexer_sync_service.py` - Sync logic
- `test_indexer_search.py` - Local search accuracy

### Integration Tests

- Test initial sync populates cache
- Test incremental sync adds new releases
- Test GUID-based deduplication
- Test cleanup removes stale entries

### Performance Tests

- Benchmark FTS5 search speed
- Compare local vs API search latency
- Measure API call reduction

## UI/API Endpoints

### New Endpoints

```python
# View indexer cache status
GET /api/indexer-cache/status
Response: {
  "providers": [
    {
      "name": "Prowlarr",
      "enabled": true,
      "last_sync": "2025-01-22T10:30:00",
      "total_releases": 15234,
      "sync_interval_minutes": 30,
      "next_sync_in_seconds": 450
    }
  ],
  "total_releases": 15234,
  "database_size_mb": 30.5,
  "oldest_release": "2024-10-22T12:00:00"
}

# Manually trigger sync for provider
POST /api/indexer-cache/sync/{provider_name}
Response: {
  "success": true,
  "releases_added": 42,
  "releases_updated": 5
}

# Get cache statistics
GET /api/indexer-cache/stats
Response: {
  "total_releases": 15234,
  "releases_by_provider": {"Prowlarr": 15234},
  "releases_last_7_days": 523,
  "database_size_mb": 30.5
}

# Clear cache (danger zone)
POST /api/indexer-cache/clear
Response: {"success": true, "releases_deleted": 15234}
```

### Settings Page UI

**New Section: "Indexer Cache"**

```
Indexer Cache Status
────────────────────
✅ Enabled
📊 15,234 releases cached (30.5 MB)
🔄 Last sync: 2 minutes ago
⏰ Next sync: in 28 minutes

Providers:
┌────────────┬──────────────┬──────────┬─────────────┐
│ Provider   │ Last Sync    │ Releases │ Status      │
├────────────┼──────────────┼──────────┼─────────────┤
│ Prowlarr   │ 2 mins ago   │ 15,234   │ ✅ Syncing  │
└────────────┴──────────────┴──────────┴─────────────┘

Actions:
[Sync Now] [Clear Cache] [View Logs]

Settings:
• Sync Interval: [30] minutes
• Cleanup Days: [90] days
• Initial Sync on Startup: [✓]
```

## Monitoring & Logs

### Log Messages

```python
# Initial sync
logger.info(f"Starting initial sync for {provider_name} (category: {category})")
logger.info(f"Initial sync complete: {provider_name} - {count} releases cached")

# Incremental sync
logger.debug(f"Incremental sync: {provider_name} - fetching latest 100 releases")
logger.info(f"Sync complete: {provider_name} - {new} new, {updated} updated")

# Errors
logger.error(f"Sync failed for {provider_name}: {error}")
logger.warning(f"Rate limit approaching for {provider_name}: {calls}/100")
```

### Metrics to Track

- Total releases cached
- Releases added per sync
- Sync duration
- API calls per hour
- Search latency (local vs API)
- Cache hit rate

## Future Enhancements

### Phase 2 Features

- **Smart sync** - Only sync categories with tracked periodicals
- **Priority sync** - Sync active periodicals more frequently
- **Multi-provider aggregation** - Merge results from multiple indexers
- **Cache warmup** - Pre-sync popular titles on startup

### Phase 3 Features

- **Distributed cache** - Share cache across multiple Curator instances
- **Cache export/import** - Backup/restore cache database
- **Advanced search** - Complex queries (date ranges, size filters, etc.)
- **Trending analysis** - Identify popular releases over time

## Success Metrics

### API Usage Reduction

- **Target:** 95%+ reduction in API calls
- **Measure:** API calls/hour before vs after

### Search Performance

- **Target:** <100ms search latency
- **Measure:** Average search response time

### User Experience

- **Target:** Zero rate limit errors
- **Measure:** Error rate in logs

### Data Freshness

- **Target:** <30 min lag for new releases
- **Measure:** Time from provider publish to cache availability

---

## Summary

This architecture transforms Curator from **API-per-search** to **local-first search** with periodic background syncing. This is the same pattern used by Prowlarr, Sonarr, and other \*arr apps to stay within API rate limits while providing fast, reliable search.

**Key Benefits:**

- 95%+ API call reduction
- Instant search results
- Rate limit safe
- Offline capability
- Better data quality

**Implementation Complexity:** Medium

- New database schema ✅
- New services (2) ✅
- Background task integration ✅
- Search router updates ✅
- UI for monitoring ✅

**Estimated Development Time:** 2-3 days for MVP, 1 week for full featured implementation
