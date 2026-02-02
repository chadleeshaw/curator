# Performance Testing Guide

This guide covers how to run performance tests for the Curator application.

## Overview

Three types of performance testing are available:

1. **API Endpoint Benchmarks** - Quick benchmarks of individual endpoints
2. **Load Testing** - Concurrent user simulation with Locust
3. **Database Query Profiling** - Database query performance analysis

## Setup

Install performance testing dependencies:

```bash
pip install -r requirements.txt
# This installs: pytest-benchmark>=4.0.0, locust>=2.20.0
```

## Running Tests

### Quick Performance Check

Run all performance benchmarks (API + Database):

```bash
make test-perf
```

### API Endpoint Benchmarks

Benchmark individual API endpoints to identify slow responses:

```bash
# Run all API benchmarks
make test-perf-api

# Or run directly with pytest
.venv/bin/python -m pytest tests/performance/test_api_benchmarks.py --benchmark-only -v

# With verbose output (shows statistics table)
.venv/bin/python -m pytest tests/performance/test_api_benchmarks.py --benchmark-only -v --benchmark-verbose
```

**What it measures:**
- Response time (min, max, mean, median)
- Standard deviation
- Operations per second
- Individual endpoint performance

**Endpoints tested:**
- `/api/version` - Version info
- `/api/periodicals` - Library listing
- `/api/periodicals/tracking` - Tracking entries
- `/api/queue/stats` - OCR queue stats
- `/api/tasks/status` - Background task status
- `/api/search/periodicals` - Search operations

### Database Query Benchmarks

Profile database queries to find bottlenecks:

```bash
# Run all database benchmarks
make test-perf-db

# Or run directly
.venv/bin/python -m pytest tests/performance/test_db_benchmarks.py --benchmark-only -v
```

**What it tests:**
- Basic queries (SELECT, COUNT)
- Filtered queries (WHERE, LIKE)
- Join operations
- Aggregations (GROUP BY, COUNT)
- Pagination (LIMIT, OFFSET)
- Bulk operations

**Example scenarios:**
- Listing magazines with pagination
- Searching by title/language/date
- Tracking with magazine joins
- OCR queue queries
- Statistics aggregations

### Load Testing with Locust

Simulate multiple concurrent users to test system capacity:

```bash
# Automated 60-second test with 20 concurrent users
make test-perf-load

# Interactive web UI (recommended for exploration)
make test-perf-load-ui
# Then open http://localhost:8089

# Custom parameters (CLI mode)
locust -f tests/performance/locustfile.py --headless \
  -u 50 -r 5 -t 120s \
  --host http://localhost:8000

# High load stress test
locust -f tests/performance/locustfile.py --headless \
  -u 100 -r 10 -t 300s \
  --host http://localhost:8000
```

**Parameters:**
- `-u` / `--users` - Number of concurrent users to simulate
- `-r` / `--spawn-rate` - Users to spawn per second
- `-t` / `--run-time` - How long to run (e.g., 60s, 5m, 2h)
- `--headless` - CLI mode without web UI
- `--host` - Target application URL

**User types:**
- `CuratorUser` - Normal users (browsing, searching)
- `AdminUser` - Admin users (heavy operations)

**Task weights:**
- View library (5x) - Most common
- View tracking (2x) - Common
- Search (1x) - Occasional
- OCR queue (2x) - Common

**Metrics provided:**
- Request count and failure rate
- Response times (min, max, avg, percentiles)
- Requests per second (RPS)
- Error types and counts

### Interpreting Results

#### pytest-benchmark Output

```
Name                              Min      Max     Mean   StdDev  Median      OPS
test_periodicals_list          12.34ms  45.67ms  23.45ms  4.56ms  22.34ms  42.65
```

- **Mean** - Average response time (target: <100ms for reads)
- **StdDev** - Consistency indicator (lower is better)
- **OPS** - Operations per second (higher is better)

#### Locust Output

```
Type     Name                  # reqs  # fails  Avg    Min    Max    Median  req/s
GET      /api/periodicals      1000    0        45ms   12ms   234ms  42ms    16.7
```

- **# fails** - Number of failed requests (target: <1%)
- **Avg** - Average response time
- **req/s** - Throughput per endpoint
- **95th/99th percentile** - Tail latency (shown in detailed view)

## Performance Targets

### Response Times
- **Read operations**: <100ms average, <500ms 95th percentile
- **Write operations**: <200ms average, <1000ms 95th percentile
- **Search operations**: <500ms average, <2000ms 95th percentile
- **Heavy operations (OCR)**: <5000ms

### Throughput
- Normal load: >50 requests/second
- Peak load: >100 requests/second with <5% failure rate

### Concurrency
- Support 50 concurrent users with acceptable performance
- Support 100 concurrent users with degraded but functional performance

## Troubleshooting

### Slow API Endpoints

1. Check database query performance:
   ```bash
   make test-perf-db
   ```

2. Look for N+1 query problems (multiple queries per request)

3. Add database indexes for frequently filtered columns:
   ```sql
   CREATE INDEX idx_magazine_title ON magazines(title);
   CREATE INDEX idx_magazine_issue_date ON magazines(issue_date);
   ```

4. Use `EXPLAIN ANALYZE` to profile specific queries

### High Load Failures

1. Check database connection pool settings
2. Verify uvicorn worker configuration
3. Monitor system resources (CPU, RAM, disk I/O)
4. Check for slow external API calls (Newsnab, download clients)

### Inconsistent Performance

1. Run benchmarks multiple times to establish baseline
2. Close other applications during testing
3. Use `--benchmark-warmup-iterations=10` for cold start issues
4. Check for background tasks affecting performance

## Advanced Usage

### Comparison Benchmarks

Save baseline and compare after optimizations:

```bash
# Save baseline
.venv/bin/python -m pytest tests/performance/test_api_benchmarks.py \
  --benchmark-only --benchmark-save=baseline

# After changes, compare
.venv/bin/python -m pytest tests/performance/test_api_benchmarks.py \
  --benchmark-only --benchmark-compare=baseline
```

### Profiling Specific Endpoints

Create custom test for specific endpoint:

```python
def test_specific_endpoint(benchmark, client, auth_headers):
    """Benchmark a specific slow endpoint"""
    def call_endpoint():
        return client.get("/api/slow-endpoint", headers=auth_headers)
    
    result = benchmark.pedantic(call_endpoint, iterations=100, rounds=10)
    assert result.status_code == 200
```

### Distributed Load Testing

Run Locust in distributed mode for extreme load:

```bash
# Terminal 1: Master
locust -f tests/performance/locustfile.py --master \
  --host http://localhost:8000

# Terminal 2+: Workers (run on same or different machines)
locust -f tests/performance/locustfile.py --worker \
  --master-host=localhost
```

## Continuous Integration

Add to CI pipeline for regression detection:

```yaml
# .github/workflows/performance.yml
- name: Run performance tests
  run: |
    make test-perf
    # Fail if response time exceeds threshold
    make test-perf-api | grep "Mean" | awk '{if ($4 > 100) exit 1}'
```

## Resources

- pytest-benchmark docs: https://pytest-benchmark.readthedocs.io/
- Locust docs: https://docs.locust.io/
- SQLAlchemy profiling: https://docs.sqlalchemy.org/en/20/faq/performance.html
