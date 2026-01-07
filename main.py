#!/usr/bin/env python3
"""
Periodical Download Manager - Main Entry Point

Run this to start the web server and periodical manager.
"""

import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from core.config import ConfigLoader

config_loader = ConfigLoader()
storage_config = config_loader.get_storage()

db_path = Path(storage_config.get("db_path", "./local/config/periodicals.db"))
download_dir = Path(storage_config.get("download_dir", "./local/downloads"))
organize_dir = Path(storage_config.get("organize_dir", "./local/data"))
cache_dir = Path(storage_config.get("cache_dir", "./local/cache"))
log_file = config_loader.get_logging().get(
    "log_file", "./local/logs/periodical_manager.log"
)
log_dir = Path(log_file).parent

for directory in [db_path.parent, download_dir, organize_dir, cache_dir, log_dir]:
    directory.mkdir(parents=True, exist_ok=True)

# Configure logging (after directories are created and config is loaded)
log_config = config_loader.get_logging()
log_level = log_config.get("level", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
)

logger = logging.getLogger(__name__)

from web.app import app

if __name__ == "__main__":
    try:
        import uvicorn

        logger.info("Starting Curator...")
        logger.info("Access the web UI at: http://localhost:8000")

        # Enable access logs only if DEBUG logging is enabled
        log_config = config_loader.get_logging()
        log_level = log_config.get("level", "INFO").upper()
        access_log = log_level == "DEBUG"

        server_config = config_loader.get_server()
        host = server_config.get("host", "0.0.0.0")
        port = server_config.get("port", 8000)

        uvicorn.run(app, host=host, port=port, access_log=access_log)

    except KeyboardInterrupt:
        logger.info("Shutting down...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
