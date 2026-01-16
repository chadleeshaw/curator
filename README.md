# 🪙 Curator

Automatically discover, download, and organize periodicals (magazines, comics, newspapers) with a modern web interface.

## Features

- 🔍 **Smart Search** - Multi-provider search with fuzzy matching to avoid duplicates
- 📥 **Auto Downloads** - Track periodicals for automatic downloads via SABnzbd/NZBGet
- 📚 **Clean Library** - Automatic organization with consistent naming and cover art
- 🤖 **OCR Metadata** - Extracts issue numbers and dates from cover images
- 🌐 **Web Interface** - Browse, search, and manage your collection

## Quick Start with Docker

### 1. Create Configuration

```bash
# Create directories
mkdir -p local/config local/data local/downloads

# Copy sample config
cp config.sample.yaml local/config/config.yaml

# Edit with your API keys
nano local/config/config.yaml
```

Add your Newsnab provider (Prowlarr recommended) and download client:

```yaml
search_providers:
  - type: newsnab
    name: Prowlarr
    enabled: true
    api_url: 'http://your-prowlarr:9696/api'
    api_key: 'your_api_key_here'

download_client:
  type: sabnzbd
  name: SABnzbd
  api_url: 'http://your-sabnzbd:8080'
  api_key: 'your_api_key_here'
```

### 2. Run with Docker

```bash
docker run -d \
  --name curator \
  -p 8000:8000 \
  -v $(pwd)/local/config:/app/local/config \
  -v $(pwd)/local/data:/app/local/data \
  -v $(pwd)/local/downloads:/app/local/downloads \
  chadleeshaw/curator:latest
```

### 3. Access the Web UI

Open http://localhost:8000 in your browser and start searching!

## Docker Options

### Low Memory Mode (< 4GB RAM)

Disable OCR to reduce memory usage:

```bash
docker run -d \
  --name curator \
  -p 8000:8000 \
  -e DISABLE_OCR=true \
  -v $(pwd)/local/config:/app/local/config \
  -v $(pwd)/local/data:/app/local/data \
  -v $(pwd)/local/downloads:/app/local/downloads \
  chadleeshaw/curator:latest
```

### Custom Port

```bash
docker run -d \
  --name curator \
  -p 3000:8000 \
  -v $(pwd)/local/config:/app/local/config \
  -v $(pwd)/local/data:/app/local/data \
  -v $(pwd)/local/downloads:/app/local/downloads \
  chadleeshaw/curator:latest
```

## Docker Compose (Recommended)

Create `docker-compose.yml`:

```yaml
version: '3.8'
services:
  curator:
    image: chadleeshaw/curator:latest
    container_name: curator
    restart: unless-stopped
    ports:
      - '8000:8000'
    volumes:
      - ./local/config:/app/local/config
      - ./local/data:/app/local/data
      - ./local/downloads:/app/local/downloads
    environment:
      - TZ=America/New_York
      # - DISABLE_OCR=true  # Uncomment for low memory
```

Then run:

```bash
docker-compose up -d
```

## Using Curator

### Search & Download

1. Navigate to **Search** in the web UI
2. Enter a periodical title (e.g., "National Geographic")
3. Choose automatic or manual mode
4. Select results to download

### Track for Auto-Downloads

1. Go to **Tracking**
2. Search for a periodical
3. Configure download preferences:
   - Track all editions
   - Track new issues only
   - Select specific editions
4. Curator will automatically download new issues

### Browse Library

View your organized collection in **Library** with:

- Cover thumbnails
- Metadata (issue dates, numbers)
- Special editions marked
- Quick file access

## Configuration Options

### Search Providers

Supports any Newsnab-compatible indexer:

```yaml
search_providers:
  - type: newsnab
    name: Prowlarr
    enabled: true
    api_url: 'http://prowlarr:9696/api'
    api_key: 'your_key'

  - type: rss
    name: MyRSS
    enabled: true
    feed_url: 'http://example.com/feed.rss'
```

### Download Clients

**SABnzbd** (recommended):

```yaml
download_client:
  type: sabnzbd
  name: SABnzbd
  api_url: 'http://sabnzbd:8080'
  api_key: 'your_key'
```

**NZBGet**:

```yaml
download_client:
  type: nzbget
  name: NZBGet
  api_url: 'http://nzbget:6789'
  username: 'nzbget'
  password: 'your_password'
```

### Storage Paths

```yaml
storage:
  db_path: './local/config/periodicals.db'
  download_dir: './local/downloads' # Where downloads arrive
  organize_dir: './local/data' # Where files are organized
  cache_dir: './local/cache'
```

### File Organization

```yaml
import:
  organization_pattern: '{category}/{title}/{title} - {date}'
  category_prefix: '_'
  enable_ocr: true
```

Results in structure:

```
local/data/
├── _Comics/
│   └── Batman/
│       └── Batman - 2024-01.pdf
└── _Magazines/
    └── National Geographic/
        └── National Geographic - 2024-01.pdf
```

## Development Setup

For local development without Docker:

```bash
# Install dependencies
pip install -r requirements.txt
npm install

# Copy config
cp config.sample.yaml local/config/config.yaml

# Run application
python main.py
```

**Run tests:**

```bash
make test           # All tests
make test-unit      # Fast unit tests only
make lint           # Check code style
make format         # Auto-format code
```

## Requirements

- **Docker**: Any recent version (Docker Desktop or Docker Engine)
- **RAM**: 4GB+ (2GB+ with `DISABLE_OCR=true`)
- **Disk**: Depends on your collection size
- **Services**: Newsnab indexer (Prowlarr) and download client (SABnzbd/NZBGet)

## Troubleshooting

**Container keeps restarting:**

- Check logs: `docker logs curator`
- If exit code 137: Out of memory - try `DISABLE_OCR=true`
- If exit code 132: CPU doesn't support AVX2 - use `DISABLE_OCR=true`

**Can't connect to download client:**

- Check `api_url` in config
- If using Docker networks, use container names (e.g., `http://sabnzbd:8080`)
- Verify API key is correct

**No search results:**

- Verify Newsnab/Prowlarr is running
- Check API key and URL in config
- View logs: `docker logs curator`

## Architecture

```
curator/
├── core/           # Configuration, auth, parsers, utilities
├── clients/        # Download clients (SABnzbd, NZBGet)
├── models/         # Database models
├── providers/      # Search providers (Newsnab, RSS)
├── services/       # Business logic (import, organize, OCR)
├── tasks/          # Background jobs (monitoring, cleanup)
├── web/            # FastAPI routes and middleware
└── static/         # Web UI (vanilla JavaScript)
```

## License

MIT License - See LICENSE file for details

## Support

- 📝 [Documentation](https://github.com/chadleeshaw/curator/wiki)
- 🐛 [Report Issues](https://github.com/chadleeshaw/curator/issues)
- 💬 [Discussions](https://github.com/chadleeshaw/curator/discussions)
