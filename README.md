# 🪙 Curator

Automatically discover, download, and organize periodicals (magazines, comics, newspapers) with a modern web interface.

## ✨ Features

- 🔍 **Smart Search** - Multi-provider search with intelligent deduplication
- 📥 **Auto Downloads** - Track periodicals for automatic downloads via SABnzbd/NZBGet
- 📚 **Clean Library** - Automatic organization with consistent naming and cover art
- 🤖 **OCR Metadata** - Extract issue numbers and dates from cover images
- 🌐 **Web Interface** - Modern, responsive UI to browse and manage your collection
- 🔄 **Background Tasks** - Automated monitoring, cleanup, and processing

## 🚀 Quick Start

## 🚀 Quick Start

### Prerequisites

- Docker installed
- Newsnab indexer (Prowlarr recommended)
- Download client (SABnzbd or NZBGet)

### 1. Setup Configuration

```bash
# Create directories
mkdir -p local/config local/data local/downloads

# Copy sample config
cp config.template.yaml local/config/config.yaml

# Edit with your settings
nano local/config/config.yaml
```

**Minimal config** - Add your provider and download client:

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

**Option A: Docker Run**

```bash
docker run -d \
  --name curator \
  -p 8000:8000 \
  -v $(pwd)/local/config:/app/local/config \
  -v $(pwd)/local/data:/app/local/data \
  -v $(pwd)/local/downloads:/app/local/downloads \
  chadleeshaw/curator:latest
```

**Option B: Docker Compose (Recommended)**

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
      # - DISABLE_OCR=true  # Uncomment for low memory mode
```

Then start:

```bash
docker-compose up -d
```

### 3. Access the Web UI

Open **http://localhost:8000** and start managing your periodicals!

## 📖 Using Curator

### Search & Download

1. **Search** → Enter periodical title (e.g., "National Geographic")
2. Choose automatic deduplication or manual provider selection
3. Select results and download

### Track for Auto-Downloads

1. **Tracking** → Search for a periodical
2. Configure preferences:
   - Track all editions
   - Track new issues only  
   - Select specific editions
3. Curator automatically downloads new issues as they're released

### Browse Library

**Library** tab shows your organized collection with:
- Cover thumbnails
- Metadata (dates, issue numbers, special editions)
- Quick file access and management

## ⚙️ Configuration

## ⚙️ Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DISABLE_OCR` | `false` | Disable OCR processing (reduces memory usage) |
| `TZ` | System | Set timezone (e.g., `America/New_York`) |
| `CURATOR_CONFIG_PATH` | `local/config/config.yaml` | Custom config file location |

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

Organize your library with custom patterns:

```yaml
import:
  organization_pattern: '{category}/{title}/{title} - {date}'
  category_prefix: '_'
  enable_ocr: true
```

**Example structure:**

```
local/data/
├── _Comics/
│   └── Batman/
│       └── Batman - 2024-01.pdf
└── _Magazines/
    └── National Geographic/
        └── National Geographic - 2024-01.pdf
```

## 🛠 Development Setup

For local development without Docker:

```bash
# Install dependencies
pip install -r requirements.txt
npm install

# Copy config
cp config.template.yaml local/config/config.yaml

# Install Git hooks (auto-runs linters before push)
make install-hooks

# Run application
python main.py
```

**Available commands:**

```bash
make test           # Run all tests
make test-unit      # Fast unit tests only
make lint           # Check code style
make ci-lint        # CI linters (matches GitHub Actions)
make format         # Auto-format code
```

The project includes a pre-push Git hook that runs `make ci-lint` automatically to ensure code quality.

## 📋 Requirements

- **Docker**: Any recent version
- **RAM**: 4GB+ recommended (2GB+ with `DISABLE_OCR=true`)
- **Disk**: Depends on collection size
- **Services**: 
  - Newsnab indexer (Prowlarr recommended)
  - Download client (SABnzbd or NZBGet)

## 🔧 Troubleshooting

### Container Issues

**Container keeps restarting:**
```bash
# Check logs
docker logs curator

# Common fixes:
# - Exit code 137: Out of memory → Add DISABLE_OCR=true
# - Exit code 132: No AVX2 support → Add DISABLE_OCR=true
```

**Can't connect to download client:**
- Verify `api_url` in config (use container names if on Docker network)
- Check API key is correct
- Ensure download client is running

**No search results:**
- Verify Prowlarr/indexer is running and accessible
- Check API key and URL in config
- Review logs: `docker logs curator`

## 🏗 Architecture

```
curator/
├── core/           # Configuration, parsers, utilities
├── models/         # Database models (SQLAlchemy)
├── providers/      # Search providers (Newsnab, RSS)
├── clients/        # Download clients (SABnzbd, NZBGet)
├── services/       # Business logic (import, organize, OCR)
├── schedulers/     # Background tasks (monitoring, cleanup)
├── web/            # FastAPI API & routers
│   └── routers/    # API endpoints (organized by domain)
└── static/         # Web UI (JavaScript ES6 modules)
    └── js/         # Frontend code (core, features, readers)
```

## 📄 License

MIT License - See [LICENSE](LICENSE) file for details.

## 💬 Support

- 📚 [Documentation](https://github.com/chadleeshaw/curator/wiki)
- 🐛 [Report Issues](https://github.com/chadleeshaw/curator/issues)
- 💭

## License

MIT License - See LICENSE file for details

## Support

- 📝 [Documentation](https://github.com/chadleeshaw/curator/wiki)
- 🐛 [Report Issues](https://github.com/chadleeshaw/curator/issues)
- 💬 [Discussions](https://github.com/chadleeshaw/curator/discussions)
