# 🪙 Curator

A modular system for discovering, downloading, and organizing periodicals (magazines, comics, newspapers) using Newsnab APIs and download clients.

## Features

- **Multi-Provider Search**: Newsnab (Prowlarr), RSS feeds, CrossRef, Wikipedia
- **Smart Deduplication**: Fuzzy matching prevents duplicate downloads
- **Metadata Enrichment**: Open Library integration for covers and metadata
- **Download Management**: SABnzbd and NZBGet support
- **Web Interface**: Modern UI for searching, browsing, and viewing
- **Organized Storage**: Automatic file organization with consistent naming

## Quick Start

### Docker (Recommended)

```bash
# Build the image
docker build -t curator .

# Run the container
docker run -d \
  --name curator \
  -p 8000:8000 \
  -v $(pwd)/local/config:/app/local/config \
  -v $(pwd)/local/data:/app/local/data \
  -v $(pwd)/local/downloads:/app/local/downloads \
  curator

```

### Python

```bash
# Install dependencies
pip install -r requirements.txt

# Set up configuration
cp config.sample.yaml local/config/config.yaml
# Edit local/config/config.yaml with your API keys and URLs

# Run the application
python main.py
```

Access the web interface at `http://localhost:8000`

## Configuration

### Initial Setup

1. Create the local config directory:
   ```bash
   mkdir -p local/config local/data local/downloads local/cache local/logs
   ```

2. Copy the sample configuration:
   ```bash
   cp config.sample.yaml local/config/config.yaml
   ```

3. Edit `local/config/config.yaml` with your settings:

```yaml
search_providers:
  - type: newsnab
    name: Prowlarr
    enabled: true
    api_url: "http://localhost:9696/api"
    api_key: "your_prowlarr_api_key"

download_client:
  type: sabnzbd
  name: SABnzbd
  api_url: "http://localhost:8080"
  api_key: "your_sabnzbd_api_key"

storage:
  db_path: "./local/config/periodicals.db"
  download_dir: "./local/downloads"
  organize_dir: "./local/data"
  cache_dir: "./local/cache"
```

### Configuration Files

- `config.sample.yaml` - Sample configuration with all available options
- `tests/config.test.yaml` - Test configuration used by CI/CD (do not edit)
- `local/config/config.yaml` - Your personal configuration (gitignored)

### Environment Variables

You can override the config file location:
```bash
export CURATOR_CONFIG_PATH=/path/to/custom/config.yaml
python main.py
```

## Usage

- **Search**: Enter a title, select automatic or manual mode, download results
- **Library**: Browse organized periodicals with covers and metadata
- **Imports**: Monitor and manually process downloads
- **Tracking**: Track specific periodicals for automated downloads

## Architecture

The application follows a modular design:

- **Providers**: Pluggable search providers (Newsnab, RSS, CrossRef, Wikipedia)
- **Clients**: Download client implementations (SABnzbd, NZBGet)
- **Processor**: Download monitoring, file import, organization, scheduling
- **Web**: FastAPI backend with modern frontend
- **Core**: Configuration, authentication, database, matching logic

## License

MIT
